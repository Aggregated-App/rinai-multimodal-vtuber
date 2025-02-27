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
    get_omft_address
)
from dotenv import load_dotenv

load_dotenv()

MAX_GAS = 300 * 10 ** 12
SOLVER_BUS_URL = os.getenv('SOLVER_BUS_URL', "https://solver-relay-v2.chaindefuser.com/rpc")

ASSET_MAP = {
    'USDC': { 
        'token_id': '17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1',
        'omft': 'eth-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.omft.near',
        'decimals': 6,
    },
    'NEAR': {
        'token_id': 'wrap.near',
        'decimals': 24,
    }
}


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


def account(account_path):
    RPC_NODE_URL = 'https://rpc.mainnet.near.org'
    content = json.load(open(os.path.expanduser(account_path), 'r'))
    near_provider = near_api.providers.JsonProvider(RPC_NODE_URL)
    key_pair = near_api.signer.KeyPair(content["private_key"])
    signer = near_api.signer.Signer(content["account_id"], key_pair)
    return near_api.account.Account(near_provider, signer, content["account_id"])


def get_asset_id(token):
    return config.to_asset_id(token)


def to_decimals(amount, token):
    return config.to_decimals(amount, token)


def register_token_storage(account, token, other_account=None):
    """Register token storage for an account"""
    account_id = other_account if other_account else account.account_id
    token_id = config.get_token_id(token)
    if not token_id:
        raise ValueError(f"Token {token} not supported")
        
    balance = account.view_function(token_id, 'storage_balance_of', {'account_id': account_id})['result']
    if not balance:
        print('Register %s for %s storage' % (account_id, token))
        account.function_call(token_id, 'storage_deposit',
            {"account_id": account_id}, MAX_GAS, 1250000000000000000000)


def sign_quote(account, quote):
    quote_data = quote.encode('utf-8')
    signature = 'ed25519:' + base58.b58encode(account.signer.sign(quote_data)).decode('utf-8')
    public_key = 'ed25519:' + base58.b58encode(account.signer.public_key).decode('utf-8')
    return Commitment(standard="raw_ed25519", payload=quote, signature=signature, public_key=public_key)


def create_token_diff_quote(account, token_in, amount_in, token_out, amount_out, quote_asset_in=None, quote_asset_out=None):
    """Create a token diff quote for swapping"""
    # Use exact asset IDs from quote if provided, otherwise fallback to config
    token_in_fmt = quote_asset_in if quote_asset_in else config.to_asset_id(token_in)
    token_out_fmt = quote_asset_out if quote_asset_out else config.to_asset_id(token_out)
    
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
                token_in_fmt: "-" + str(amount_in),  # Make amount_in negative
                token_out_fmt: str(amount_out)  # Keep amount_out positive
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
    Returns:
        Transaction result
    """
    try:
        return account.function_call(
            'wrap.near',
            'near_deposit',
            {},
            MAX_GAS,
            int(amount * 10**24)  # Convert to yoctoNEAR
        )
    except Exception as e:
        print(f"Error wrapping NEAR: {str(e)}")
        raise e


def intent_deposit(account, token, amount):
    """Deposit tokens into the intents contract"""
    token_id = config.get_token_id(token)
    if not token_id:
        raise ValueError(f"Token {token} not supported")
        
    register_token_storage(account, token, other_account="intents.near")
    account.function_call(token_id, 'ft_transfer_call', {
        "receiver_id": "intents.near",
        "amount": config.to_decimals(amount, token),
        "msg": ""
    }, MAX_GAS, 1)


def register_intent_public_key(account):
    account.function_call("intents.near", "add_public_key", {
        "public_key": "ed25519:" + base58.b58encode(account.signer.public_key).decode('utf-8')
    }, MAX_GAS, 1)


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
    # Match the exact format of working curl request
    rpc_request = {
        "jsonrpc": "2.0",
        "id": 1,  # Changed from "dontcare" to 1
        "method": "quote",
        "params": [{
            "defuse_asset_identifier_in": request.asset_in["asset"],
            "defuse_asset_identifier_out": request.asset_out["asset"],
            "exact_amount_in": str(request.asset_in["amount"])
            # Removed min_deadline_ms to match working curl
        }]
    }
    
    print("\n=== QUOTE REQUEST ===")
    print(f"URL: {SOLVER_BUS_URL}")
    print(f"Request: {json.dumps(rpc_request, indent=2)}")
    
    try:
        response = requests.post(SOLVER_BUS_URL, json=rpc_request)
        print("\n=== QUOTE RESPONSE ===")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code != 200:
            print(f"Error from solver bus: {response.text}")
            return []
            
        result = response.json()
        if "error" in result:
            print(f"RPC error: {result['error']}")
            return []
            
        # Extract quotes directly from result array
        quotes = result.get("result", [])  # Changed from result.get("result", {}).get("quotes", [])
        if not quotes:
            print("No quotes available for this swap")
            
        return quotes
            
    except Exception as e:
        print(f"Error: {str(e)}")
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


def intent_swap(account, token_in, amount_in, token_out, chain_out="eth"):
    """Swap tokens using intents"""
    print(f"\nCreating swap request:")
    print(f"Token in: {token_in}")
    print(f"Amount in: {amount_in}")
    print(f"Token out: {token_out} on {chain_out}")
    
    request = IntentRequest().asset_in(token_in, amount_in).asset_out(token_out, chain=chain_out)
    print(f"Serialized request: {request.serialize()}")
    
    options = fetch_options(request)
    print(f"Received options: {options}")
    
    best_option = select_best_option(options)
    if not best_option:
        raise Exception("No valid quotes received")
        
    # Use the exact asset IDs and amounts from the quote
    quote = create_token_diff_quote(
        account, 
        token_in, 
        best_option['amount_in'],
        token_out, 
        best_option['amount_out'],
        quote_asset_in=best_option['defuse_asset_identifier_in'],
        quote_asset_out=best_option['defuse_asset_identifier_out']
    )
    
    signed_intent = PublishIntent(signed_data=quote, quote_hashes=[best_option['quote_hash']])
    response = publish_intent(signed_intent)
    return response


def get_future_deadline(days=365):
    """Generate a deadline timestamp that's X days in the future"""
    from datetime import datetime, timedelta, UTC
    future_date = datetime.now(UTC) + timedelta(days=days)
    return future_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def intent_withdraw(account, destination_address, token, amount, network='near'):
    """
    Withdraw tokens from the intents contract
    Args:
        account: NEAR account
        destination_address: Address to withdraw to
        token: Token symbol (e.g., 'USDC', 'NEAR')
        amount: Amount to withdraw
        network: Target chain (default: 'near')
    """
    nonce = base64.b64encode(random.getrandbits(256).to_bytes(32, byteorder='big')).decode('utf-8')
    
    # Get token configuration
    token_config = get_token_by_symbol(token, network)
    if not token_config:
        raise ValueError(f"Token {token} not supported on network {network}")

    # Prepare quote
    quote = Quote(
        signer_id=account.account_id,
        nonce=nonce,
        verifying_contract="intents.near",
        deadline=get_future_deadline(),
        intents=[
            {
                "intent": "ft_withdraw",
                "token": token_config["chains"]["near"]["token_id"],
                "receiver_id": destination_address,
                "amount": to_decimals(amount, token)
            }
        ]
    )

    signed_quote = sign_quote(account, json.dumps(quote))
    signed_intent = PublishIntent(signed_data=signed_quote)
    return publish_intent(signed_intent)

#get intent balance
def get_intent_balance(account, token):
    """
    Get the balance of a specific token in the intents contract for an account
    Args:
        account: NEAR account
        token: Token symbol (e.g., 'USDC', 'NEAR', 'ETH')
    Returns:
        float: The balance in human-readable format
    """
    token_id = get_token_id(token)
    print(f"Checking balance for token: {token}")
    print(f"Token ID: {token_id}")
    
    # Convert to nep141 format as seen in the event logs
    nep141_token_id = f"nep141:{token_id}"
    print(f"NEP141 Token ID: {nep141_token_id}")
    print(f"Account ID: {account.account_id}")
    
    if not token_id:
        raise ValueError(f"Token {token} not supported")
    
    # Call the mt_balance_of view method on intents contract
    try:
        balance_response = account.view_function(
            'intents.near',  # Call intents contract
            'mt_balance_of',   # Use mt_balance_of method
            {
                'token_id': nep141_token_id,  # Use the NEP141 format
                'account_id': account.account_id  # Get OUR balance
            }
        )
        print(f"Raw balance response: {balance_response}")
        
        # Convert from base units to human readable
        if balance_response and 'result' in balance_response:
            human_balance = from_decimals(balance_response['result'], token)
            print(f"Converted balance: {human_balance}")
            return human_balance
    except Exception as e:
        print(f"Error getting balance: {str(e)}")
    return 0.0

def get_all_intent_balances(account):
    """
    Get all token balances in the intents contract for an account
    Args:
        account: NEAR account
    Returns:
        dict: Dictionary of token symbols to balances
    """
    balances = {}
    for token in config.get_supported_tokens(chain='near'):
        try:
            balance = get_intent_balance(account, token['symbol'])
            if balance > 0:
                balances[token['symbol']] = balance
        except Exception as e:
            print(f"Error getting balance for {token['symbol']}: {str(e)}")
    return balances


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
    account1 = account("<>")
    # print(intent_withdraw(account1, "<near account>", "USDC", 1))
    print(intent_withdraw(account1, "<eth address>", "USDC", 1, network='eth'))