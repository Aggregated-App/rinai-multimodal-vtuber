import pytest

import os
import sys
from dotenv import load_dotenv
from near_api.account import Account
from near_api.signer import KeyPair, Signer
from near_api.providers import JsonProvider
from decimal import Decimal
import time
import random
import base64
import json
import base58

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from clients.near_Intents_client.intents_client import (
    intent_deposit, 
    smart_withdraw,
    intent_swap,
    get_intent_balance,
    wrap_near,
    publish_intent,
    Quote,
    Intent,
    PublishIntent,
    get_future_deadline,
    sign_quote,
    MAX_GAS
)
from clients.near_Intents_client import config  # Import the config module
from clients.near_Intents_client.config import (
    get_token_by_symbol,
    get_defuse_asset_id,
    to_decimals,
    from_decimals
)


#RUN THIS TEST WITH: pytest tests/test_intents_client.py

# Load environment variables
load_dotenv()

# Simple fixture for account setup - reuses your existing initialization
@pytest.fixture
def account():
    account_id = os.getenv('NEAR_ACCOUNT_ID')
    private_key = os.getenv('NEAR_PRIVATE_KEY')
    provider = JsonProvider(os.getenv('NEAR_RPC_URL'))
    key_pair = KeyPair(private_key)
    signer = Signer(account_id, key_pair)
    return Account(provider, signer)

@pytest.fixture
def setup_account(account):
    """Setup account with registered public key if needed"""
    try:
        print("\nChecking public key registration...")
        public_key = "ed25519:" + base58.b58encode(account.signer.public_key).decode('utf-8')
        
        # Check if already registered
        result = account.view_function(
            "intents.near",
            "has_public_key",
            {"public_key": public_key}
        )
        
        if not result['result']:
            print("Public key not registered, registering now...")
            register_intent_public_key(account)
            time.sleep(2)  # Wait for registration
        else:
            print("Public key already registered")
            
        return account
    except Exception as e:
        pytest.fail(f"Failed to check/register public key: {str(e)}")

def test_near_deposit_and_withdraw(account):
    """Test depositing and withdrawing NEAR"""
    
    # Check initial balance
    initial_balance = get_intent_balance(account, "NEAR")
    account_state = account.provider.get_account(account.account_id)
    print(f"Initial NEAR balance in intents account: {initial_balance}")
    print(f"Initial NEAR balance: {from_decimals(account_state['amount'], 'NEAR')}")
    
    # Deposit 0.01 NEAR
    deposit_amount = 0.01
    print(f"\nDepositing {deposit_amount} NEAR...")
    try:
        # First wrap the NEAR
        wrap_result = wrap_near(account, deposit_amount)
        time.sleep(3)
        
        # Then deposit
        result = intent_deposit(account, "NEAR", deposit_amount)
        print("Deposit successful:", result)
    except Exception as e:
        print("Deposit failed:", str(e))
        return
    
    # Check balance after deposit
    new_balance = get_intent_balance(account, "NEAR")
    account_state = account.provider.get_account(account.account_id)
    print(f"NEAR balance after deposit in Intents account: {new_balance}")
    print(f"NEAR account balance after deposit in NEAR account: {from_decimals(account_state['amount'], 'NEAR')}")
    
    # Withdraw 0.005 NEAR using smart_withdraw
    withdraw_amount = 0.005
    print(f"\nWithdrawing {withdraw_amount} NEAR...")
    try:
        result = smart_withdraw(
            account=account,
            token="NEAR",
            amount=withdraw_amount,
            destination_chain="near"  # Optional, defaults to "near"
        )
        print("Withdrawal successful:", result)
    except Exception as e:
        print("Withdrawal failed:", str(e))
    
    # Check final balance
    time.sleep(3)
    final_balance = get_intent_balance(account, "NEAR")
    print(f"Final NEAR balance in intents: {final_balance}")

def test_near_usdc_swap(account):
    """Test getting quotes and swapping NEAR to USDC"""
    initial_balances = {
        "NEAR": get_intent_balance(account, "NEAR"),
        "USDC": get_intent_balance(account, "USDC", chain="eth")  # Note: Check ETH chain USDC
    }
    print("\nInitial Balances:", json.dumps(initial_balances, indent=2))
    
    # Validate tokens exist before starting test
    near_token = config.get_token_by_symbol("NEAR")
    usdc_token = config.get_token_by_symbol("USDC", "eth")
    
    if not near_token or not usdc_token:
        pytest.skip("Required tokens not configured")
    
    def get_balances():
        """Get NEAR and USDC balances"""
        eth_balance = get_intent_balance(account, "USDC", chain="eth")
        near_balance = get_intent_balance(account, "USDC", chain="near")
        print(f"\nDetailed USDC Balances:")
        print(f"ETH Chain: {eth_balance}")
        print(f"NEAR Chain: {near_balance}")
        return {
            "NEAR": get_intent_balance(account, "NEAR"),
            "USDC": {
                "eth": eth_balance,
                "near": near_balance
            }
        }
    
    # Deposit NEAR
    deposit_amount = 0.1
    print(f"\nDepositing {deposit_amount} NEAR...")
    try:
        wrap_result = wrap_near(account, deposit_amount)
        time.sleep(3)
        result = intent_deposit(account, "NEAR", deposit_amount)
        print("Deposit successful:", result)
    except Exception as e:
        print("Deposit failed:", str(e))
        return
    
    # Execute swap
    try:
        swap_result = intent_swap(account, "NEAR", deposit_amount, "USDC", chain_out="eth")
        print("\nSwap Result Details:")
        print(json.dumps(swap_result, indent=2))
        time.sleep(3)
        
        # Get post-swap balances
        print("\nBalances After Swap:")
        post_swap_balances = get_balances()
        
        # Use config's decimal conversion instead of hardcoded 6
        swap_amount = config.from_decimals(swap_result['amount_out'], 'USDC')
        print(f"\nAttempting to withdraw {swap_amount} USDC")
        print(f"Current ETH-USDC balance: {post_swap_balances['USDC']['eth']}")
        
        # Use smart_withdraw for USDC withdrawal
        try:
            print(f"\nWithdrawing {swap_amount} USDC to NEAR wallet...")
            withdrawal_result = smart_withdraw(
                account=account,
                token="USDC",
                amount=swap_amount,
                destination_chain="near",        # Token lives on ETH chain
                destination_address=account.account_id  # But send to NEAR wallet
            )
            print("\nWithdrawal Result:")
            print(json.dumps(withdrawal_result, indent=2))
            time.sleep(3)
            
            final_balance = get_intent_balance(account, "USDC", chain="eth")
            print(f"\nFinal USDC balance on ETH chain: {final_balance}")
            
        except Exception as e:
            print(f"\nWithdrawal Error: {str(e)}")
            print(f"Current USDC balance on ETH chain: {get_intent_balance(account, 'USDC', chain='eth')}")
        
    except Exception as e:
        print("Swap failed:", str(e))
        return
    
    # Check final balances
    post_withdrawal = get_balances()
    print("\nPost-Withdrawal Balances:")
    print(f"NEAR: {post_withdrawal['NEAR']}")
    print(f"USDC: {post_withdrawal['USDC']}")
    
    return {
        "initial_balances": initial_balances,
        "final_balances": post_withdrawal,
        "post_withdrawal": post_withdrawal,
        "amount_swapped": deposit_amount,
        "amount_received": swap_amount
    }

def test_near_sol_swap(account):
    """Test swapping NEAR to SOL and withdrawing to Solana wallet"""
    def get_balances():
        """Get NEAR and SOL balances"""
        return {
            "NEAR": get_intent_balance(account, "NEAR"),
            "SOL": get_intent_balance(account, "SOL", chain="solana")
        }

    initial_balances = get_balances()
    print("\nInitial Balances:", json.dumps(initial_balances, indent=2))
    
    # Deposit NEAR
    deposit_amount = 0.4
    print(f"\nDepositing {deposit_amount} NEAR...")
    try:
        wrap_result = wrap_near(account, deposit_amount)
        time.sleep(3)
        result = intent_deposit(account, "NEAR", deposit_amount)
        print("Deposit successful:", result)
    except Exception as e:
        print("Deposit failed:", str(e))
        return
    
    # Execute swap
    try:
        print("\nExecuting NEAR to SOL swap...")
        swap_result = intent_swap(account, "NEAR", deposit_amount, "SOL", chain_out="solana")
        print("\nSwap Result Details:")
        print(json.dumps(swap_result, indent=2))
        time.sleep(3)
        
        # Get post-swap balances
        print("\nBalances After Swap:")
        post_swap_balances = get_balances()
        print(json.dumps(post_swap_balances, indent=2))
        
        # Use config's decimal conversion
        swap_amount = config.from_decimals(swap_result['amount_out'], 'SOL')
        print(f"\nAttempting to withdraw {swap_amount} SOL")
        print(f"Current SOL balance: {post_swap_balances['SOL']}")
        
        # Use smart_withdraw for SOL withdrawal to Solana wallet
        try:
            print(f"\nWithdrawing {swap_amount} SOL to Solana wallet...")
            withdrawal_result = smart_withdraw(
                account=account,
                token="SOL",
                amount=swap_amount,
                destination_chain="solana",     # Token lives on Solana chain
                destination_address=os.getenv('SOLANA_ACCOUNT_ID')  # Send to Solana wallet
            )
            print("\nWithdrawal Result:")
            print(json.dumps(withdrawal_result, indent=2))
            time.sleep(3)
            
            final_balances = get_balances()
            print("\nFinal Balances:")
            print(json.dumps(final_balances, indent=2))
            
        except Exception as e:
            print(f"\nWithdrawal Error: {str(e)}")
            print(f"Current SOL balance: {get_intent_balance(account, 'SOL', chain='solana')}")
        
    except Exception as e:
        print("Swap failed:", str(e))
        return
    
    return {
        "initial_balances": initial_balances,
        "final_balances": final_balances,
        "amount_swapped": deposit_amount,
        "amount_received": swap_amount
    }

if __name__ == "__main__":
    print("Running intents client tests...")
    test_near_deposit_and_withdraw()
    test_near_usdc_swap()
    test_near_sol_swap()