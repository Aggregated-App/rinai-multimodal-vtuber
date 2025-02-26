import os
import sys
from dotenv import load_dotenv
from near_api.account import Account
from near_api.signer import KeyPair, Signer
from near_api.providers import JsonProvider
from decimal import Decimal
import time

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from clients.near_Intents_client.intents_client import (
    intent_deposit, 
    intent_withdraw,
    intent_swap,
    get_intent_balance,
    wrap_near
)
from clients.near_Intents_client.config import (
    get_token_by_symbol,
    to_asset_id,
    to_decimals,
    from_decimals
)

# Load environment variables
load_dotenv()

def test_near_deposit_and_withdraw():
    """Test depositing and withdrawing NEAR"""
    # Initialize account directly
    account_id = os.getenv('NEAR_ACCOUNT_ID')
    private_key = os.getenv('NEAR_PRIVATE_KEY')
    provider = JsonProvider(os.getenv('NEAR_RPC_URL'))
    key_pair = KeyPair(private_key)
    signer = Signer(account_id, key_pair)
    account = Account(provider, signer)
    
    print("\nTesting NEAR deposit and withdraw:")
    
    # Check initial balance
    initial_balance = get_intent_balance(account, "NEAR")
    account_state = provider.get_account(account.account_id)
    print(f"Initial NEAR balance in intents: {initial_balance}")
    print(f"Initial NEAR account balance: {float(account_state['amount'])/10**24}")
    
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
    account_state = provider.get_account(account.account_id)
    print(f"NEAR balance after deposit: {new_balance}")
    print(f"NEAR account balance after deposit: {float(account_state['amount'])/10**24}")
    
    # Withdraw 0.5 NEAR
    withdraw_amount = 0.05
    print(f"\nWithdrawing {withdraw_amount} NEAR...")
    try:
        result = intent_withdraw(account, account.account_id, "NEAR", withdraw_amount)
        print("Withdrawal successful:", result)
    except Exception as e:
        print("Withdrawal failed:", str(e))
    
    # Check final balance
    final_balance = get_intent_balance(account, "NEAR")
    print(f"Final NEAR balance in intents: {final_balance}")

def test_near_usdc_swap():
    """Test getting quotes and swapping NEAR to USDC"""
    # Initialize account directly
    account_id = os.getenv('NEAR_ACCOUNT_ID')
    private_key = os.getenv('NEAR_PRIVATE_KEY')
    provider = JsonProvider(os.getenv('NEAR_RPC_URL'))
    key_pair = KeyPair(private_key)
    signer = Signer(account_id, key_pair)
    account = Account(provider, signer)
    
    print("\nTesting NEAR to USDC swap:")
    
    # Check initial balances
    near_balance = get_intent_balance(account, "NEAR")
    usdc_balance = get_intent_balance(account, "USDC")
    print(f"Initial balances - NEAR: {near_balance}, USDC: {usdc_balance}")
    
    # Get quote for 0.1 NEAR to USDC (changed from 1.0)
    deposit_amount = 0.1
    print(f"\nDepositing {deposit_amount} NEAR first...")
    try:
        # First wrap the NEAR
        wrap_result = wrap_near(account, deposit_amount)
        time.sleep(3)  # Wait for wrap to complete
        
        # Then deposit the wrapped NEAR
        result = intent_deposit(account, "NEAR", deposit_amount)
        print("Deposit successful:", result)
        time.sleep(3)  # Wait for deposit to complete
        
        # Check balances after deposit
        near_balance = get_intent_balance(account, "NEAR")
        print(f"NEAR balance after deposit: {near_balance}")
    except Exception as e:
        print("Deposit failed:", str(e))
        return
    
    # Now try the swap with 0.1 NEAR
    amount_in = 0.1
    print(f"\nGetting quote for {amount_in} NEAR to USDC (ETH)...")
    try:
        # Execute the swap specifying ETH chain for USDC (make sure you use correct diffues asset id)
        print(f"Executing swap of {amount_in} NEAR to USDC (ETH)...")
        result = intent_swap(account, "NEAR", amount_in, "USDC", chain_out="eth")
        print("Swap successful:", result)
    except Exception as e:
        print("Swap failed:", str(e))
        return
    
    # Check final balances
    final_near = get_intent_balance(account, "NEAR")
    final_usdc = get_intent_balance(account, "USDC")
    print(f"Final balances - NEAR: {final_near}, USDC: {final_usdc}")

if __name__ == "__main__":
    print("Running intents client tests...")
    test_near_deposit_and_withdraw()
    test_near_usdc_swap()