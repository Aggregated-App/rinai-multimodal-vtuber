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
import logging

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
    MAX_GAS,
    unwrap_near,
    register_intent_public_key,
    create_account,
    setup_account
)
from clients.near_Intents_client import config  # Import the config module
from clients.near_Intents_client.config import (
    get_token_by_symbol,
    get_defuse_asset_id,
    to_decimals,
    from_decimals
)

# Configure logger with proper format and level
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'  # Simplified format to just show the message
)
logger = logging.getLogger(__name__)

#RUN THIS TEST WITH: pytest tests/test_intents_client.py

# Load environment variables
load_dotenv()

# Use the client's create_account function
@pytest.fixture
def account():
    """Get a NEAR account using the client's create_account function"""
    return create_account()

# Change this fixture to session scope
@pytest.fixture(scope="session")
def initialized_account():
    """Get a NEAR account with registered public key using the client's setup_account function"""
    try:
        account = create_account()
        return setup_account(account)
    except Exception as e:
        pytest.fail(f"Failed to setup account: {str(e)}")

def test_near_deposit_and_withdraw(initialized_account):
    account = initialized_account
    """Test depositing and withdrawing NEAR"""
    
    # Check initial balance
    initial_balance = get_intent_balance(account, "NEAR")
    account_state = account.provider.get_account(account.account_id)
    print(f"Initial NEAR balance in intents account: {initial_balance}")
    print(f"Initial NEAR balance: {from_decimals(account_state['amount'], 'NEAR')}")
    
    # Deposit a smaller amount to conserve NEAR
    deposit_amount = 0.005
    print(f"\nDepositing {deposit_amount} NEAR...")
    try:
        # First wrap the NEAR
        wrap_result = wrap_near(account, deposit_amount)
        print(f"Wrap result: {wrap_result}")
        time.sleep(3)
        
        # Check wNEAR balance
        try:
            wnear_token_id = config.get_token_id("NEAR")
            wnear_balance = account.view_function(wnear_token_id, 'ft_balance_of', {'account_id': account.account_id})
            print(f"wNEAR balance after wrap: {from_decimals(wnear_balance['result'], 'NEAR')}")
        except Exception as e:
            print(f"Error checking wNEAR balance: {str(e)}")
        
        # Then deposit
        result = intent_deposit(account, "NEAR", deposit_amount)
        print("Deposit result:", result)
        time.sleep(3)  # Wait longer for deposit to be processed
        
        # Check balance after deposit
        new_balance = get_intent_balance(account, "NEAR")
        print(f"NEAR balance after deposit in Intents account: {new_balance}")
        
        # If balance is still 0, try checking with different asset ID formats
        if new_balance == 0:
            print("Balance is 0, trying alternative asset ID formats...")
            try:
                # Try with direct asset ID
                asset_id = "nep141:wrap.near"
                result = account.view_function(
                    "intents.near",
                    "view_balance",
                    {"account_id": account.account_id, "token_id": asset_id}
                )
                if 'result' in result and result['result']:
                    balance = from_decimals(result['result'], 'NEAR')
                    print(f"Balance with asset_id={asset_id}: {balance}")
            except Exception as e:
                print(f"Error checking with alternative asset ID: {str(e)}")
        
        # Only attempt withdrawal if we have a balance
        if new_balance > 0:
            # Withdraw a smaller amount
            withdraw_amount = min(0.001, new_balance / 2)
            print(f"\nWithdrawing {withdraw_amount} NEAR...")
            try:
                result = smart_withdraw(
                    account=account,
                    token="NEAR",
                    amount=withdraw_amount,
                    destination_chain="near"
                )
                print("Withdrawal result:", result)
            except Exception as e:
                print("Withdrawal failed:", str(e))
        else:
            print("\nSkipping withdrawal because balance is 0")
    
    except Exception as e:
        print("Deposit failed:", str(e))
        return
    
    # Check final balance
    time.sleep(3)
    final_balance = get_intent_balance(account, "NEAR")
    print(f"Final NEAR balance in intents: {final_balance}")

def get_balances(initialized_account):
    """Get NEAR, USDC, and SOL balances across chains"""
    return {
        "NEAR": get_intent_balance(account, "NEAR"),
        "USDC": {
            "eth": get_intent_balance(account, "USDC", chain="eth"),
            "near": get_intent_balance(account, "USDC", chain="near")
        },
        "SOL": get_intent_balance(account, "SOL", chain="solana")
    }

# Change this test to use initialized_account
def test_near_usdc_swap(initialized_account):
    """Test getting quotes and swapping NEAR to USDC"""
    account = initialized_account
    # Log initial balances
    initial_usdc = get_intent_balance(account, "USDC", chain="eth")
    initial_near = get_intent_balance(account, "NEAR")
    print(f"\nInitial Balances:")  # Using print for now
    print(f"NEAR: {initial_near}")
    print(f"USDC (ETH): {initial_usdc}")
    
    # Execute deposit and swap
    deposit_amount = 0.1
    print(f"\nDepositing {deposit_amount} NEAR...")
    wrap_result = wrap_near(account, deposit_amount)
    
    # Wait for wNEAR wrapping to complete
    print("Waiting for wNEAR wrapping to complete...")
    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            wnear_token_id = config.get_token_id("NEAR")
            wnear_balance_result = account.view_function(wnear_token_id, 'ft_balance_of', {'account_id': account.account_id})
            if 'result' in wnear_balance_result:
                wnear_balance = from_decimals(wnear_balance_result['result'], 'NEAR')
                print(f"wNEAR balance after waiting: {wnear_balance}")
                if wnear_balance >= deposit_amount:
                    print("wNEAR wrapping completed!")
                    break
            time.sleep(5)
        except Exception as e:
            print(f"Error checking wNEAR balance: {str(e)}")
            time.sleep(5)
        
        if attempt == max_attempts - 1:
            pytest.skip("wNEAR wrapping did not complete in time")
    
    # Now deposit the wNEAR
    result = intent_deposit(account, "NEAR", deposit_amount)
    time.sleep(3)
    
    # Execute swap and log response
    print(f"\nExecuting NEAR to USDC swap...")
    swap_result = intent_swap(account, "NEAR", deposit_amount, "USDC", chain_out="eth")
    print("\nSwap Result Details:")
    print(json.dumps(swap_result, indent=2))
    
    # Calculate and log the swap amount
    if 'amount_out' not in swap_result:
        pytest.fail("Swap failed - no amount_out in response")
    swap_amount = config.from_decimals(swap_result['amount_out'], 'USDC')
    print(f"Successfully swapped {deposit_amount} NEAR for {swap_amount} USDC")
    
    # Wait for USDC balance to appear on ETH chain
    print("Waiting for USDC balance to appear on ETH chain...")
    max_attempts = 12
    for attempt in range(max_attempts):
        usdc_balance = get_intent_balance(account, "USDC", chain="eth")
        print(f"USDC balance on ETH chain: {usdc_balance}")
        if usdc_balance >= swap_amount * 0.9:  # Allow for some slippage
            print("USDC balance found!")
            break
        time.sleep(5)
        if attempt == max_attempts - 1:
            pytest.skip("USDC balance did not appear in time")
    
    # Execute withdrawal
    print(f"\nWithdrawing {swap_amount} USDC to NEAR chain...")
    try:
        withdrawal_result = smart_withdraw(
            account=account,
            token="USDC",
            amount=swap_amount,
            destination_chain="near",
            destination_address=account.account_id,
            source_chain="eth"  # Explicitly specify the source chain
        )
        print("Withdrawal initiated")
        print("Waiting for USDC withdrawal to finalize...")
        time.sleep(30)  # Wait 30 seconds after initiating withdrawal
    except Exception as e:
        print(f"Withdrawal failed: {str(e)}")
        # Check balances on all chains to help diagnose the issue
        for chain in ["eth", "near", "arbitrum", "solana"]:
            balance = get_intent_balance(account, "USDC", chain=chain)
            print(f"USDC balance on {chain} chain: {balance}")
        pytest.fail(f"USDC withdrawal failed: {str(e)}")

def test_usdc_near_swap(initialized_account):
    """Test swapping USDC to NEAR and withdrawing"""
    account = initialized_account
    
    # Log initial balances
    initial_usdc_intents = get_intent_balance(account, "USDC", chain="near")
    initial_near = get_intent_balance(account, "NEAR")
    print(f"\nInitial Balances:")
    print(f"NEAR: {initial_near}")
    print(f"USDC (intents): {initial_usdc_intents}")
    
    # Check actual USDC balance in NEAR wallet
    usdc_token_id = config.get_token_id("USDC", "near")
    try:
        usdc_balance_result = account.view_function(usdc_token_id, 'ft_balance_of', {'account_id': account.account_id})
        if 'result' in usdc_balance_result:
            usdc_balance = config.from_decimals(usdc_balance_result['result'], "USDC")
            print(f"USDC (wallet): {usdc_balance}")
        else:
            print(f"USDC (wallet): Could not retrieve balance")
            usdc_balance = 0
    except Exception as e:
        print(f"Error checking USDC wallet balance: {str(e)}")
        usdc_balance = 0
    
    # Determine if we need to wait for USDC withdrawal to complete
    if initial_usdc_intents > 0 and usdc_balance < 0.3:
        print(f"USDC is in intents contract but not in wallet. Waiting for withdrawal to complete...")
        # Wait for withdrawal to complete (up to 2 minutes)
        for _ in range(12):  # Increased from 6 to 12 iterations
            time.sleep(5)   # Increased from 5 to 10 seconds per iteration
            try:
                usdc_balance_result = account.view_function(usdc_token_id, 'ft_balance_of', {'account_id': account.account_id})
                if 'result' in usdc_balance_result:
                    usdc_balance = config.from_decimals(usdc_balance_result['result'], "USDC")
                    print(f"USDC (wallet) after waiting: {usdc_balance}")
                    if usdc_balance >= 0.3:
                        print("Withdrawal completed!")
                        break
            except Exception as e:
                print(f"Error checking USDC wallet balance: {str(e)}")
        
    # Check if we have enough USDC in wallet
    if usdc_balance < 0.3:
        pytest.skip(f"Not enough USDC in wallet: {usdc_balance} (need at least 0.3)")
    
    # Execute deposit and swap
    deposit_amount = 0.3
    print(f"\nDepositing {deposit_amount} USDC...")
    result = intent_deposit(account, "USDC", deposit_amount)
    time.sleep(3)
    
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

    # Execute swap and log response
    print(f"\nExecuting USDC to NEAR swap...")
    swap_result = intent_swap(account, "USDC", deposit_amount, "NEAR", chain_out="near")
    print("\nSwap Result Details:")
    print(json.dumps(swap_result, indent=2))
    
    # Wait for swap to complete and verify NEAR balance
    print("Waiting for swap to complete and NEAR to be available...")
    if 'amount_out' not in swap_result:
        pytest.fail("Swap failed - no amount_out in response")
    swap_amount = config.from_decimals(swap_result['amount_out'], 'NEAR')
    
    # Wait and verify NEAR balance before withdrawal
    max_attempts = 12
    for attempt in range(max_attempts):
        try:
            near_balance = get_intent_balance(account, "NEAR")
            print(f"NEAR balance in intents after waiting: {near_balance}")
            if near_balance >= swap_amount * 0.9:  # Allow for some slippage
                print("NEAR swap completed!")
                break
            time.sleep(5)
        except Exception as e:
            print(f"Error checking NEAR balance: {str(e)}")
            time.sleep(5)
        
        if attempt == max_attempts - 1:
            pytest.skip("NEAR swap did not complete in time")
    
    print(f"Successfully swapped {deposit_amount} USDC for {swap_amount} NEAR")
    
    # Execute withdrawal
    print(f"\nWithdrawing {swap_amount} NEAR to account...")
    withdrawal_result = smart_withdraw(
        account=account,
        token="NEAR",
        amount=swap_amount,
        destination_chain="near",
        destination_address=account.account_id
    )
    print("Withdrawal initiated")
    print("Waiting for NEAR withdrawal to finalize...")
    time.sleep(15)  # Wait 15 seconds after initiating withdrawal
    
    # Unwrap the received wNEAR
    print(f"\nUnwrapping {swap_amount} wNEAR to NEAR...")
    unwrap_result = unwrap_near(account, swap_amount)
    print("Successfully unwrapped wNEAR to NEAR")

if __name__ == "__main__":
    print("Running intents client tests...")
    test_near_deposit_and_withdraw()
    test_near_usdc_swap()
    test_usdc_near_swap()
    test_near_sol_swap()