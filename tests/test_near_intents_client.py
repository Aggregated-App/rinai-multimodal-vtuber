import pytest
import json
import os
from dotenv import load_dotenv

from src.clients.near_intents_client.operations import IntentOperations
from src.clients.near_intents_client.client import NearIntentsClient
from src.clients.near_intents_client.account import IntentAccount
from src.clients.near_intents_client.intent import IntentRequest
from src.clients.near_intents_client.exceptions import IntentExecutionError
from src.clients.near_intents_client.config import ASSET_MAP, MINIMUM_AMOUNTS, NEAR_RPC_URL

load_dotenv()

@pytest.fixture
def account():
    """Create real NEAR account from environment"""
    account_id = os.getenv("NEAR_ACCOUNT_ID")
    private_key = os.getenv("NEAR_PRIVATE_KEY")
    
    if not account_id or not private_key:
        pytest.skip("NEAR_ACCOUNT_ID and NEAR_PRIVATE_KEY required in .env")
    
    return IntentAccount(account_id, private_key, NEAR_RPC_URL)

@pytest.fixture
async def client(account):
    """Create real NearIntentsClient instance"""
    client = NearIntentsClient(account)
    await client.initialize()  # Client handles registration internally
    return client

@pytest.fixture(autouse=True)
async def cleanup_client(client):
    """Cleanup fixture that runs automatically"""
    yield
    if client and hasattr(client, 'session') and client.session:
        await client.session.close()

class TestIntentOperations:
    """Test suite for IntentOperations"""

    @pytest.mark.asyncio
    async def test_intent_deposit(self, client):
        """Test NEAR deposit to intent contract"""
        client = await client  # Await the client fixture
        try:
            result = await client.operations.intent_deposit(
                token="NEAR",
                amount=MINIMUM_AMOUNTS["NEAR"]
            )
            assert result is not None
            print(f"\nDeposit result: {json.dumps(result, indent=2)}")
        except IntentExecutionError as e:
            if "insufficient balance" in str(e).lower():
                pytest.skip("Insufficient balance for deposit")
            raise

    @pytest.mark.asyncio
    async def test_intent_withdraw(self, client):
        """Test token withdrawal"""
        client = await client  # Await the client fixture
        try:
            result = await client.operations.intent_withdraw(
                token="NEAR",
                amount=0.05,
                destination_address=client.account.account_id
            )
            assert result is not None
            print(f"\nWithdraw result: {json.dumps(result, indent=2)}")
        except IntentExecutionError as e:
            if "insufficient balance" in str(e).lower():
                pytest.skip("Insufficient balance for withdrawal")
            raise

    @pytest.mark.asyncio
    async def test_get_quotes(self, client):
        """Test getting quotes from solver for NEAR to ETH USDC swap"""
        client = await client  # Await the client fixture
        try:
            quotes = await client.get_quotes(
                token_in="NEAR",
                amount_in=MINIMUM_AMOUNTS["NEAR"],
                token_out="USDC"
            )
            
            if quotes is None:
                pytest.skip("No quotes available from solver")
            
            assert isinstance(quotes, list)
            if quotes:
                best_quote = client.operations.select_best_quote(quotes)
                assert best_quote is not None
                assert "quote_hash" in best_quote
                assert "amount_out" in best_quote
                print(f"\nBest quote for NEAR -> ETH USDC: {json.dumps(best_quote, indent=2)}")
        except IntentExecutionError as e:
            if "insufficient balance" in str(e).lower():
                pytest.skip("Insufficient balance for swap")
            raise

    @pytest.mark.asyncio
    async def test_swap_execution(self, client):
        """Test complete swap execution"""
        client = await client  # Await the client fixture
        try:
            result = await client.operations.swap(
                token_in="NEAR",
                amount_in=MINIMUM_AMOUNTS["NEAR"],
                token_out="USDC",
                slippage=0.01
            )
            assert result is not None
            assert "status" in result
            print(f"\nSwap result: {json.dumps(result, indent=2)}")
        except IntentExecutionError as e:
            if "insufficient balance" in str(e).lower():
                pytest.skip("Insufficient balance for swap")
            raise
