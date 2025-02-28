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

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from clients.near_Intents_client.intents_client import (
    intent_deposit, 
    intent_withdraw,
    intent_swap,
    get_intent_balance,
    wrap_near,
    publish_intent,
    Quote,
    Intent,
    PublishIntent,
    get_future_deadline,
    sign_quote,
    MAX_GAS,
    withdraw_from_intents,
    withdraw_from_chain_to_near
)
from clients.near_Intents_client.config import (
    get_token_by_symbol,
    get_defuse_asset_id,
    to_decimals
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

def test_near_deposit_and_withdraw(account):
    """Test depositing and withdrawing NEAR"""
    
    # Check initial balance
    initial_balance = get_intent_balance(account, "NEAR")
    account_state = account.provider.get_account(account.account_id)
    print(f"Initial NEAR balance in intents account: {initial_balance}")
    print(f"Initial NEAR balance: {float(account_state['amount'])/10**24}")
    
    # Deposit 0.1 NEAR
    deposit_amount = 0.1
    print(f"\nDepositing {deposit_amount} NEAR...")
    try:
        # First wrap the NEAR
        wrap_result = wrap_near(account, deposit_amount)
        time.sleep(3)  # Back to using sleep since wait_for_transaction isn't available
        
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
    print(f"NEAR account balance after deposit in NEAR account: {float(account_state['amount'])/10**24}")
    
    # Withdraw 0.5 NEAR
    withdraw_amount = 0.05
    print(f"\nWithdrawing {withdraw_amount} NEAR...")
    try:
        result = intent_withdraw(account, account.account_id, "NEAR", withdraw_amount)
        print("Withdrawal successful:", result)
    except Exception as e:
        print("Withdrawal failed:", str(e))
    
    # Check final balance
    time.sleep(3)  # Add delay after withdraw
    final_balance = get_intent_balance(account, "NEAR")
    print(f"Final NEAR balance in intents: {final_balance}")

def test_near_usdc_swap(account):
    """Test getting quotes and swapping NEAR to USDC"""
    
    def get_balances():
        """Get NEAR and USDC balances"""
        eth_balance = get_intent_balance(account, "USDC", chain="eth")
        near_balance = get_intent_balance(account, "USDC", chain="near")
        print(f"\nDetailed USDC Balances:")
        print(f"ETH Chain: {eth_balance}")
        print(f"NEAR Chain: {near_balance}")
        return {
            "NEAR": get_intent_balance(account, "NEAR"),
            "USDC": eth_balance
        }
    
    # Check initial balances
    initial_balances = get_balances()
    print("\nInitial Balances:")
    print(json.dumps(initial_balances, indent=2))
    
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
        
        swap_amount = float(swap_result['amount_out']) / (10**6)
        print(f"\nAttempting to withdraw {swap_amount} USDC")
        print(f"Current ETH-USDC balance: {post_swap_balances['USDC']}")
        
        # Add withdrawal to NEAR chain
        try:
            withdrawal_result = withdraw_from_chain_to_near(
                account=account,
                token="USDC",
                amount=swap_amount,
                source_chain="eth"
            )
            print("\nWithdrawal to NEAR Result:")
            print(json.dumps(withdrawal_result, indent=2))
            time.sleep(3)
            
            # Check final balances after withdrawal
            final_balances = get_balances()
            print("\nFinal Balances After NEAR Withdrawal:")
            print(json.dumps(final_balances, indent=2))
            
        except Exception as e:
            print("\nNEAR Withdrawal Error:")
            print(f"Error Type: {type(e).__name__}")
            print(f"Error Message: {str(e)}")
            print("\nCurrent Balances:")
            get_balances()
        
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

if __name__ == "__main__":
    print("Running intents client tests...")
    test_near_deposit_and_withdraw()
    test_near_usdc_swap()