from typing import TypedDict, List, Dict, Union
import borsh_construct
import os
import json
import base64
import base58
import random
import requests
import near_api
from . import config
from clients.near_Intents_client.config import (
    get_token_id,
    to_asset_id,
    to_decimals,
    from_decimals,
    get_token_by_symbol,
    get_omft_address,
    get_defuse_asset_id
)
from dotenv import load_dotenv
import time
import logging

load_dotenv()

MAX_GAS = 300 * 10 ** 12
SOLVER_BUS_URL = os.getenv('SOLVER_BUS_URL', "https://solver-relay-v2.chaindefuser.com/rpc")

# Configure logger
logger = logging.getLogger(__name__)

class Intent(TypedDict):
    intent: str
    diff: Dict[str, str]


class Quote(TypedDict):
    nonce: str
    signer_id: str
    verifying_contract: str
    deadline: str
    intents: List[Intent]


def quote_to_borsh(quote):
    QuoteSchema = borsh_construct.CStruct(
        'nonce' / borsh_construct.String,
        'signer_id' / borsh_construct.String,
        'verifying_contract' / borsh_construct.String,
        'deadline' / borsh_construct.String,
        'intents' / borsh_construct.Vec(borsh_construct.CStruct(
            'intent' / borsh_construct.String,
            'diff' / borsh_construct.HashMap(borsh_construct.String, borsh_construct.String)
        ))
    )
    return QuoteSchema.build(quote)


class AcceptQuote(TypedDict):
    nonce: str
    recipient: str
    message: str


class Commitment(TypedDict):
    standard: str
    payload: Union[AcceptQuote, str]
    signature: str
    public_key: str


class SignedIntent(TypedDict):
    signed: List[Commitment]
    

class PublishIntent(TypedDict):
    signed_data: Commitment
    quote_hashes: List[str] = []


def get_asset_id(token):
    return config.to_asset_id(token)


def register_token_storage(account, token, destination_address=None, other_account=None):
    """
    Register storage for a token contract
    
    Args:
        account: NEAR account
        token: Token symbol (e.g., 'USDC', 'NEAR')
        destination_address: Address to register (defaults to account.account_id)
        other_account: Another account to register (optional)
    
    Returns:
        bool: True if registration was successful or already registered
    """
    if token == "NEAR":
        return True  # NEAR token doesn't need registration
        
    destination_address = destination_address or account.account_id
    token_id = config.get_token_id(token, "near")
    
    if not token_id:
        logger.error(f"Token {token} not supported on NEAR chain")
        return False
    
    # Register the main account
    success = _register_single_account(account, token_id, destination_address)
    
    # Register the other account if provided
    if other_account and success:
        other_success = _register_single_account(account, token_id, other_account)
        return success and other_success
        
    return success


def _register_single_account(account, token_id, account_to_register):
    """Helper function to register a single account with a token contract"""
    logger.info(f"Checking if {account_to_register} is registered with token contract {token_id}...")
    
    try:
        # Check if already registered
        storage_balance = account.view_function(
            token_id,
            'storage_balance_of',
            {'account_id': account_to_register}
        )
        
        logger.info(f"Storage balance check result: {storage_balance}")
        
        if storage_balance and 'result' in storage_balance and storage_balance['result']:
            logger.info(f"Account {account_to_register} already registered with token contract")
            return True
            
        # Not registered, need to register
        logger.info(f"Account {account_to_register} not registered with token contract. Registering...")
        
        # Use the exact yoctoNEAR amount as an integer (not a string)
        try:
            # The key fix: Use an integer for amount, not a string
            deposit_amount = 1250000000000000000000  # 0.00125 NEAR in yoctoNEAR
            
            result = account.function_call(
                token_id,
                'storage_deposit',
                {'account_id': account_to_register},
                gas=MAX_GAS,
                amount=deposit_amount  # Integer, not string
            )
            
            logger.info(f"Registration result: {result}")
        except Exception as reg_error:
            logger.error(f"Error during registration function call: {str(reg_error)}")
            return False
        
        # Verify registration was successful
        time.sleep(5)  # Wait for transaction to complete
        try:
            storage_balance = account.view_function(
                token_id,
                'storage_balance_of',
                {'account_id': account_to_register}
            )
            
            logger.info(f"Storage balance check after registration: {storage_balance}")
            
            if storage_balance and 'result' in storage_balance and storage_balance['result']:
                logger.info(f"Successfully registered {account_to_register} with token contract")
                return True
            else:
                logger.error(f"Failed to register {account_to_register} with token contract")
                return False
        except Exception as check_error:
            logger.error(f"Error checking registration status: {str(check_error)}")
            return False
            
    except Exception as e:
        logger.error(f"Error in registration process: {str(e)}")
        return False


def sign_quote(account, quote):
    quote_data = quote.encode('utf-8')
    signature = 'ed25519:' + base58.b58encode(account.signer.sign(quote_data)).decode('utf-8')
    public_key = 'ed25519:' + base58.b58encode(account.signer.public_key).decode('utf-8')
    return Commitment(standard="raw_ed25519", payload=quote, signature=signature, public_key=public_key)


def create_token_diff_quote(account, token_in, amount_in, token_out, amount_out, quote_asset_in=None, quote_asset_out=None):
    """Create a token diff quote for swapping"""
    # Use config's asset ID helpers
    token_in_fmt = quote_asset_in if quote_asset_in else config.get_defuse_asset_id(token_in)
    token_out_fmt = quote_asset_out if quote_asset_out else config.get_defuse_asset_id(token_out)
    
    if not token_in_fmt or not token_out_fmt:
        raise ValueError(f"Token {token_in} or {token_out} not supported")
        
    nonce = base64.b64encode(random.getrandbits(256).to_bytes(32, byteorder='big')).decode('utf-8')
    quote = json.dumps(Quote(
        signer_id=account.account_id,
        nonce=nonce,
        verifying_contract="intents.near",
        deadline=get_future_deadline(),
        intents=[
            Intent(intent='token_diff', diff={
                token_in_fmt: f"-{str(amount_in)}",
                token_out_fmt: str(amount_out)
            })
        ]
    ))
    return sign_quote(account, quote)


def submit_signed_intent(account, signed_intent):
    account.function_call("intents.near", "execute_intents", signed_intent, MAX_GAS, 0)


def wrap_near(account, amount):
    """
    Wrap NEAR into wNEAR
    Args:
        account: NEAR account
        amount: Amount of NEAR to wrap
    """
    try:
        # Use config's decimal conversion instead of hardcoded
        amount_base = config.to_decimals(amount, "NEAR")
        if not amount_base:
            raise ValueError("Invalid NEAR amount")
            
        return account.function_call(
            'wrap.near',
            'near_deposit',
            {},
            MAX_GAS,
            int(amount_base)
        )
    except Exception as e:
        logger.error(f"Error wrapping NEAR: {str(e)}")
        raise e


def unwrap_near(account, amount):
    """
    Unwrap wNEAR back to NEAR
    Args:
        account: NEAR account
        amount: Amount of wNEAR to unwrap
    """
    try:
        # Use config's decimal conversion
        amount_base = config.to_decimals(amount, "NEAR")
        if not amount_base:
            raise ValueError("Invalid NEAR amount")
            
        return account.function_call(
            'wrap.near',
            'near_withdraw',
            {"amount": amount_base},
            MAX_GAS,
            1  # Attach exactly 1 yoctoNEAR as required by the contract
        )
    except Exception as e:
        logger.error(f"Error unwrapping NEAR: {str(e)}")
        raise e


def intent_deposit(account, token, amount):
    """Deposit tokens into the intents contract"""
    # Get token details from config
    token_details = config.get_token_by_symbol(token)
    if not token_details:
        raise ValueError(f"Token {token} not supported")
    
    # Get the correct token ID for the NEAR chain
    if "chains" in token_details and "near" in token_details["chains"]:
        token_id = token_details["chains"]["near"]["token_id"]
    else:
        raise ValueError(f"Token {token} not available on NEAR chain")
    
    logger.info(f"Depositing {amount} {token} using token_id: {token_id}")
    
    # Check current balance before deposit
    try:
        current_balance = account.view_function(token_id, 'ft_balance_of', {'account_id': account.account_id})
        logger.info(f"Current {token} balance: {current_balance}")
        
        if 'result' in current_balance:
            human_balance = from_decimals(current_balance['result'], token)
            logger.info(f"Current {token} balance (human readable): {human_balance}")
            
            if human_balance < amount:
                logger.error(f"Insufficient {token} balance: have {human_balance}, need {amount}")
                raise ValueError(f"Insufficient {token} balance: have {human_balance}, need {amount}")
    except Exception as e:
        logger.warning(f"Could not check {token} balance: {str(e)}")
    
    # Register storage if needed (for both user and intents contract)
    try:
        register_token_storage(account, token, other_account="intents.near")
    except Exception as e:
        logger.error(f"Error registering token storage: {str(e)}")
        raise e
    
    # Use config's decimal conversion
    amount_base = config.to_decimals(amount, token)
    if not amount_base:
        raise ValueError(f"Invalid amount for {token}")
    
    logger.info(f"Transferring {amount_base} base units of {token} to intents.near")
    
    # Execute the transfer
    try:
        result = account.function_call(token_id, 'ft_transfer_call', {
            "receiver_id": "intents.near",
            "amount": amount_base,
            "msg": ""
        }, MAX_GAS, 1)
        
        logger.info(f"Transfer result: {result}")
        return result
    except Exception as e:
        logger.error(f"Transfer failed: {str(e)}")
        
        # Check if this is a balance issue
        if "doesn't have enough balance" in str(e):
            try:
                # Check balance again to confirm
                balance_check = account.view_function(token_id, 'ft_balance_of', {'account_id': account.account_id})
                if 'result' in balance_check:
                    human_balance = from_decimals(balance_check['result'], token)
                    logger.error(f"Confirmed insufficient balance: have {human_balance}, need {amount}")
            except Exception:
                pass
        
        raise e


def register_intent_public_key(account):
    """
    Register a public key with the intents contract if not already registered
    
    Args:
        account: NEAR account
    
    Returns:
        str: Status message indicating if key was registered or already exists
    """
    try:
        # Format the public key correctly
        public_key = "ed25519:" + base58.b58encode(account.signer.public_key).decode('utf-8')
        logger.info(f"Checking if public key {public_key} is registered for {account.account_id}")
        
        # Check if already registered - INCLUDE ACCOUNT_ID in the parameters
        try:
            result = account.view_function(
                "intents.near",
                "has_public_key",
                {
                    "account_id": account.account_id,  # Add account_id parameter
                    "public_key": public_key
                }
            )
            
            if not result['result']:
                logger.info(f"Registering public key for account {account.account_id}")
                # Include account_id in the registration call as well
                account.function_call("intents.near", "add_public_key", {
                    "account_id": account.account_id,  # Add account_id parameter
                    "public_key": public_key
                }, MAX_GAS, 1)
                time.sleep(3)  # Wait longer for registration to complete
                return "Key registered"
            else:
                logger.info(f"Public key already registered for account {account.account_id}")
                return "Key already registered"
        except Exception as e:
            # If the view function fails, try to register the key directly
            logger.warning(f"Error checking if public key is registered: {str(e)}")
            logger.info(f"Attempting to register public key directly")
            
            # Include account_id in the registration call
            account.function_call("intents.near", "add_public_key", {
                "account_id": account.account_id,  # Add account_id parameter
                "public_key": public_key
            }, MAX_GAS, 1)
            time.sleep(3)  # Wait longer for registration to complete
            return "Key registration attempted"
    except Exception as e:
        logger.error(f"Error registering public key: {str(e)}")
        raise e


def register_intents_storage(account):
    """Register storage with the intents contract"""
    try:
        # Check if already registered
        storage_balance = account.view_function("intents.near", 'storage_balance_of', {'account_id': account.account_id})
        logger.info(f"Intents storage balance check result: {storage_balance}")
        
        if not storage_balance.get('result'):
            logger.info(f"Registering storage for {account.account_id} with intents.near")
            result = account.function_call(
                "intents.near",
                'storage_deposit',  # Changed from register_account to storage_deposit
                {'account_id': account.account_id},
                MAX_GAS,
                1250000000000000000000  # 0.00125 NEAR
            )
            logger.info(f"Storage registration result: {result}")
            time.sleep(2)
            
            # Verify registration was successful
            verify_storage = account.view_function("intents.near", 'storage_balance_of', {'account_id': account.account_id})
            logger.info(f"Storage registration verification: {verify_storage}")
            if not verify_storage.get('result'):
                logger.error(f"Storage registration failed for {account.account_id} with intents.near")
                return "Storage registration failed"
            return "Storage registered"
        else:
            logger.info(f"Account {account.account_id} already registered with intents.near")
            return "Already registered"
    except Exception as e:
        logger.error(f"Error registering intents storage: {str(e)}")
        return f"Error: {str(e)}"


class IntentRequest(object):
    """IntentRequest is a request to perform an action on behalf of the user."""
    
    def __init__(self, request=None, thread=None, min_deadline_ms=120000):
        self.request = request
        self.thread = thread
        self.min_deadline_ms = min_deadline_ms

    def asset_in(self, asset_name, amount, chain="near"):
        self.asset_in = {
            "asset": config.to_asset_id(asset_name, chain),
            "amount": config.to_decimals(amount, asset_name)
        }
        return self

    def asset_out(self, asset_name, amount=None, chain="eth"):
        self.asset_out = {
            "asset": config.to_asset_id(asset_name, chain),
            "amount": config.to_decimals(amount, asset_name) if amount else None,
            "chain": chain
        }
        return self

    def serialize(self):
        message = {
            "defuse_asset_identifier_in": self.asset_in["asset"],
            "defuse_asset_identifier_out": self.asset_out["asset"],
            "exact_amount_in": str(self.asset_in["amount"]),
            "exact_amount_out": str(self.asset_out["amount"]),
            "min_deadline_ms": self.min_deadline_ms,
        }
        if self.asset_in["amount"] is None:
            del message["exact_amount_in"]
        if self.asset_out["amount"] is None:
            del message["exact_amount_out"]
        return message


def fetch_options(request):
    """Fetches the trading options from the solver bus."""
    rpc_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "quote",
        "params": [{
            "defuse_asset_identifier_in": request.asset_in["asset"],
            "defuse_asset_identifier_out": request.asset_out["asset"],
            "exact_amount_in": str(request.asset_in["amount"])
        }]
    }
    
    try:
        response = requests.post(SOLVER_BUS_URL, json=rpc_request)
        if response.status_code != 200:
            logger.error(f"Error from solver bus: {response.text}")
            return []
            
        result = response.json()
        if "error" in result:
            logger.error(f"RPC error: {result['error']}")
            return []
            
        quotes = result.get("result", [])
        if not quotes:
            logger.info("No quotes available for this swap")
            
        return quotes
            
    except Exception as e:
        logger.error(f"Error fetching quotes: {str(e)}")
        return []


def publish_intent(signed_intent):
    """Publishes the signed intent to the solver bus."""
    rpc_request = {
        "id": "dontcare",
        "jsonrpc": "2.0",
        "method": "publish_intent",
        "params": [signed_intent]
    }
    response = requests.post(SOLVER_BUS_URL, json=rpc_request)
    return response.json()


def select_best_option(options):
    """Selects the best option from the list of options."""
    best_option = None
    for option in options:
        if not best_option or option["amount_out"] > best_option["amount_out"]:
            best_option = option
    return best_option


def intent_swap(account, token_in: str, amount_in: float, token_out: str, chain_out: str = "eth") -> dict:
    """Execute a token swap using intents."""
    # Validate tokens exist on respective chains
    if not config.get_token_by_symbol(token_in):
        raise ValueError(f"Token {token_in} not supported")
    if not config.get_token_by_symbol(token_out, chain_out):
        raise ValueError(f"Token {token_out} not supported on {chain_out}")
    
    # Convert amount using config helper
    amount_in_base = config.to_decimals(amount_in, token_in)
    
    # Get quote from solver
    request = IntentRequest().asset_in(token_in, amount_in).asset_out(token_out, chain=chain_out)
    options = fetch_options(request)
    best_option = select_best_option(options)
    
    if not best_option:
        raise Exception("No valid quotes received")
    
    # Create quote using proper asset identifiers
    quote = create_token_diff_quote(
        account,
        token_in,
        amount_in_base,
        token_out,
        best_option['amount_out'],
        quote_asset_in=best_option['defuse_asset_identifier_in'],
        quote_asset_out=best_option['defuse_asset_identifier_out']
    )
    
    # Submit intent
    signed_intent = PublishIntent(
        signed_data=quote,
        quote_hashes=[best_option['quote_hash']]
    )
    
    return {
        **publish_intent(signed_intent),
        'amount_out': best_option['amount_out']
    }


def get_future_deadline(days=365):
    """Generate a deadline timestamp that's X days in the future"""
    from datetime import datetime, timedelta, UTC
    future_date = datetime.now(UTC) + timedelta(days=days)
    return future_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def get_intent_balance(account, token, chain="near"):
    """
    Get the balance of a specific token in the intents contract for an account
    Args:
        account: NEAR account
        token: Token symbol (e.g., 'USDC', 'NEAR', 'ETH')
        chain: Chain name (e.g., 'near', 'eth') - defaults to 'near'
    Returns:
        float: The balance in human-readable format
    """
    # Get the defuse asset ID for the specific chain
    nep141_token_id = get_defuse_asset_id(token, chain)
    
    if not nep141_token_id:
        raise ValueError(f"Token {token} not supported on chain {chain}")
    
    try:
        balance_response = account.view_function(
            'intents.near',
            'mt_balance_of',
            {
                'token_id': nep141_token_id,
                'account_id': account.account_id
            }
        )
        
        if balance_response and 'result' in balance_response:
            token_info = get_token_by_symbol(token)
            decimals = token_info['decimals'] if token_info else 6
            return float(balance_response['result']) / (10 ** decimals)
    except Exception as e:
        logger.error(f"Error getting balance: {str(e)}")
    return 0.0


def smart_withdraw(account, token: str, amount: float, destination_address: str = None, destination_chain: str = None, source_chain: str = None) -> dict:
    """
    Smart router that picks the appropriate withdrawal method
    Args:
        account: NEAR account
        token: Token symbol (e.g., 'USDC', 'NEAR')
        amount: Amount to withdraw
        destination_address: Address to withdraw to (defaults to account.account_id)
        destination_chain: Chain to withdraw to (defaults to "near")
        source_chain: Chain where token currently is (e.g., "eth" for ETH-USDC)
    """
    if not destination_chain:
        destination_chain = "near"
        
    if destination_chain == "near":
        return withdraw_same_chain(account, token, amount, destination_address, source_chain)
    else:
        return withdraw_cross_chain(account, token, amount, destination_chain, destination_address)


def withdraw_same_chain(account, token: str, amount: float, destination_address: str = None, source_chain: str = None) -> dict:
    """
    Withdraw tokens to same chain (e.g., NEAR to NEAR wallet)
    If token is on another chain, handles conversion first
    """
    token_id = config.get_token_id(token, "near")
    destination_address = destination_address or account.account_id
    
    logger.info(f"=== WITHDRAW SAME CHAIN ===")
    logger.info(f"Token: {token}")
    logger.info(f"Token ID: {token_id}")
    logger.info(f"Amount: {amount}")
    logger.info(f"Destination: {destination_address}")
    logger.info(f"Source Chain: {source_chain}")
    
    # For NEAR token, we're always on NEAR chain
    if token == "NEAR":
        source_chain = "near"
    elif source_chain is None:
        # Check balances to determine source chain
        for chain in ["eth", "near", "arbitrum", "solana"]:
            balance = get_intent_balance(account, token, chain=chain)
            if balance >= amount:
                source_chain = chain
                break
                
    if not source_chain:
        raise ValueError(f"Could not find source chain for {token} with sufficient balance")
    
    logger.info(f"Determined source chain: {source_chain}")
    
    # Check if token needs conversion to NEAR chain
    current_chain_asset = config.get_defuse_asset_id(token, source_chain)
    near_chain_asset = config.get_defuse_asset_id(token, "near")
    
    logger.info(f"Current chain asset: {current_chain_asset}")
    logger.info(f"NEAR chain asset: {near_chain_asset}")
    
    if current_chain_asset != near_chain_asset and source_chain != "near":
        logger.info(f"\nConverting {token} from {source_chain} to NEAR chain...")
        # Need conversion quote first
        request = IntentRequest().asset_in(token, amount, chain=source_chain).asset_out(token, chain="near")
        options = fetch_options(request)
        best_option = select_best_option(options)
        
        if not best_option:
            raise Exception(f"No conversion quote available for {token} to NEAR chain")
        
        logger.info(f"Conversion quote: {best_option}")
        
        # Create and publish conversion quote first
        conversion_quote = create_token_diff_quote(
            account,
            token,
            config.to_decimals(amount, token),
            token,
            best_option['amount_out'],
            quote_asset_in=best_option['defuse_asset_identifier_in'],
            quote_asset_out=best_option['defuse_asset_identifier_out']
        )
        
        # Submit conversion intent
        conversion_intent = PublishIntent(
            signed_data=conversion_quote,
            quote_hashes=[best_option['quote_hash']]
        )
        
        conversion_result = publish_intent(conversion_intent)
        logger.info("\nConversion Result:")
        logger.info(json.dumps(conversion_result, indent=2))
        
        # Use converted amount for withdrawal
        amount_base = best_option['amount_out']
        time.sleep(3)  # Give time for conversion to complete
    else:
        # No conversion needed, use direct amount
        amount_base = config.to_decimals(amount, token)
    
    logger.info(f"Final amount_base for withdrawal: {amount_base}")
    
    # Register storage for the token before withdrawal
    if token != "NEAR":  # NEAR token doesn't need registration
        logger.info(f"\n=== REGISTERING TOKEN STORAGE ===")
        logger.info(f"Token: {token}")
        logger.info(f"Token ID: {token_id}")
        logger.info(f"Destination: {destination_address}")
        
        registration_success = register_token_storage(account, token, destination_address)
        logger.info(f"Registration success: {registration_success}")
        
        if not registration_success:
            logger.warning(f"Failed to register {destination_address} with {token} token. Withdrawal may fail.")
            
        # Double-check registration
        try:
            storage_balance = account.view_function(
                token_id,
                'storage_balance_of',
                {'account_id': destination_address}
            )
            logger.info(f"Storage balance check after registration: {storage_balance}")
            
            if not storage_balance.get('result'):
                logger.warning(f"Account still not registered with {token} token after registration attempt")
        except Exception as e:
            logger.error(f"Error checking storage balance: {str(e)}")
    
    # Now do the withdrawal with converted amount
    logger.info(f"\n=== CREATING WITHDRAWAL INTENT ===")
    quote = Quote(
        signer_id=account.account_id,
        nonce=base64.b64encode(random.getrandbits(256).to_bytes(32, byteorder='big')).decode('utf-8'),
        verifying_contract="intents.near",
        deadline=get_future_deadline(),
        intents=[{
            "intent": "ft_withdraw",
            "token": token_id,
            "receiver_id": destination_address,
            "amount": str(amount_base)
        }]
    )
    
    logger.info(f"Withdrawal quote: {json.dumps(quote, indent=2)}")
    
    signed_quote = sign_quote(account, json.dumps(quote))
    signed_intent = PublishIntent(signed_data=signed_quote)
    
    logger.info(f"Publishing withdrawal intent...")
    result = publish_intent(signed_intent)
    logger.info(f"Withdrawal result: {json.dumps(result, indent=2)}")
    
    return result


def withdraw_cross_chain(account, token: str, amount: float, destination_chain: str, destination_address: str = None) -> dict:
    """Withdraw tokens to different chain"""
    # Get token config and validate
    token_config = config.get_token_by_symbol(token)
    if not token_config:
        raise ValueError(f"Token {token} not supported")
    
    # Get destination address
    if not destination_address:
        if destination_chain == "solana":
            destination_address = os.getenv('SOLANA_ACCOUNT_ID')
        elif destination_chain in ["eth", "arbitrum", "base"]:
            destination_address = os.getenv('ETHEREUM_ACCOUNT_ID')
            
    if not destination_address:
        raise ValueError(f"No destination address provided for {destination_chain} chain")
    
    # Get the exact token ID that matches our balance
    defuse_asset_id = config.get_defuse_asset_id(token, destination_chain)
    if not defuse_asset_id:
        raise ValueError(f"No defuse asset ID for {token} on {destination_chain}")
        
    # Remove 'nep141:' prefix to get the token ID
    token_id = defuse_asset_id.replace('nep141:', '')
    
    logger.info(f"\nWithdrawal Details:")
    logger.info(f"Token: {token}")
    logger.info(f"Chain: {destination_chain}")
    logger.info(f"Token ID: {token_id}")
    logger.info(f"Destination: {destination_address}")
    
    amount_base = config.to_decimals(amount, token)
    
    quote = Quote(
        signer_id=account.account_id,
        nonce=base64.b64encode(random.getrandbits(256).to_bytes(32, byteorder='big')).decode('utf-8'),
        verifying_contract="intents.near",
        deadline=get_future_deadline(),
        intents=[{
            "intent": "ft_withdraw",
            "token": token_id,
            "receiver_id": token_id,
            "amount": amount_base,
            "memo": f"WITHDRAW_TO:{destination_address}"
        }]
    )
    
    signed_quote = sign_quote(account, json.dumps(quote))
    signed_intent = PublishIntent(signed_data=signed_quote)
    return publish_intent(signed_intent)


def deposit_token(account, token: str, amount: float, source_chain: str = None) -> dict:
    """Deposit any supported token into intents contract"""
    if token == "NEAR":
        # Existing NEAR flow
        wrap_result = wrap_near(account, amount)
        time.sleep(3)
        return intent_deposit(account, token, amount)
    else:
        # New flow for other tokens
        token_id = config.get_token_id(token, source_chain)
        if not token_id:
            raise ValueError(f"Token {token} not supported on {source_chain}")
            
        # Register storage if needed
        register_token_storage(account, token)
        
        # Execute deposit
        return intent_deposit(account, token, amount)


def create_account():
    """Create a NEAR account using environment variables"""
    account_id = os.getenv('NEAR_ACCOUNT_ID')
    private_key = os.getenv('NEAR_PRIVATE_KEY')
    provider = near_api.providers.JsonProvider(os.getenv('NEAR_RPC_URL', 'https://rpc.mainnet.near.org'))
    key_pair = near_api.signer.KeyPair(private_key)
    signer = near_api.signer.Signer(account_id, key_pair)
    return near_api.account.Account(provider, signer, account_id)


def setup_account(account=None):
    """
    Setup account with registered public key if needed
    
    Args:
        account: NEAR account (optional, will create from env vars if not provided)
        
    Returns:
        Account: NEAR account with registered public key
    """
    if account is None:
        account = create_account()
        
    try:
        # Register public key
        key_status = register_intent_public_key(account)
        logger.info(f"Key registration status: {key_status}")
        if key_status == "Key registered":
            time.sleep(2)  # Wait for registration
            
        # Register storage
        storage_status = register_intents_storage(account)
        logger.info(f"Storage registration status: {storage_status}")
        
        return account
    except Exception as e:
        logger.error(f"Failed to setup account: {str(e)}")
        raise e

if __name__ == "__main__":
    # Trade between two accounts directly.
    # account1 = utils.account(
    #     "<>")
    # account2 = utils.account(
    #     "<>")
    # register_intent_public_key(account1)
    # register_intent_public_key(account2)
    # intent_deposit(account1, 'NEAR', 1)
    # intent_deposit(account2, 'USDC', 10)
    # quote1 = create_token_diff_quote(account1, 'NEAR', '1', 'USDC', '8')
    # quote2 = create_token_diff_quote(account2, 'USDC', '8', 'NEAR', '1')
    # signed_intent = SignedIntent(signed=[quote1, quote2])
    # print(json.dumps(signed_intent, indent=2))
    # submit_signed_intent(account1, signed_intent)

    # Trade via solver bus.
    # account1 = account("")
    # print(intent_swap(account1, 'NEAR', 1, 'USDC'))

    # Withdraw to external address.
    account1 = create_account()
    # print(intent_withdraw(account1, "<near account>", "USDC", 1))
    print(intent_withdraw(account1, "<eth address>", "USDC", 1, network='eth'))