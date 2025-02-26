from typing import Dict, Any, List, Optional
import json
import base64
import base58
import aiohttp
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from .exceptions import ValidationError, IntentExecutionError
from .config import ASSET_MAP, MAX_GAS
from .operations import IntentOperations
from .intent import IntentRequest, Commitment
from .account import IntentAccount

logger = logging.getLogger(__name__)

class NearIntentsClient:
    """Client for interacting with NEAR Intents protocol"""
    
    def __init__(self, account):
        self.account = account
        self.session = None
        self.initialized = False
        self.operations = IntentOperations(self)

    async def initialize(self) -> None:
        """Initialize client session and register public key"""
        if self.initialized:
            return
            
        try:
            # 1. Create session
            self.session = aiohttp.ClientSession()
            
            # 2. Check if key is already registered to avoid multiple attempts
            try:
                # Try to view the key first
                result = await self.account.view_function(
                    "intents.near",
                    "get_public_key",
                    {"account_id": self.account.account_id}
                )
                logger.info("Public key already registered")
            except Exception:
                # Key not found, register it
                logger.info("Registering public key...")
                await self.account.function_call(
                    "intents.near",
                    "add_public_key",
                    {"public_key": f"ed25519:{self.account.public_key_str}"},
                    MAX_GAS,
                    1
                )
                logger.info("Public key registered successfully")
            
            self.initialized = True
            logger.info("Client initialized successfully")
            
        except Exception as e:
            await self.close()
            raise IntentExecutionError(f"Failed to initialize client: {e}")

    def sign_quote(self, message: str) -> str:
        """Sign a quote message for intent creation"""
        try:
            message_bytes = message.encode('utf-8')
            signature = self.account.sign(message_bytes)
            return base58.b58encode(signature).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to sign quote: {e}")
            raise IntentExecutionError(f"Failed to sign quote: {e}")

    async def ensure_initialized(self) -> None:
        """Ensure client is initialized before operations"""
        if not self.initialized:
            await self.initialize()

    async def close(self) -> None:
        """Close client session and cleanup"""
        if self.session:
            await self.session.close()
            self.session = None
        self.initialized = False

    async def register_token_storage(self, token: str) -> None:
        """
        Register storage for a specific token
        Required before first deposit of each token type
        """
        await self.ensure_initialized()
        try:
            await self.account.function_call(
                ASSET_MAP[token]['token_id'],
                'storage_deposit',
                {
                    "account_id": "intents.near",
                    "registration_only": True
                },
                MAX_GAS,
                100000000000000000000000  # 0.1 NEAR
            )
        except Exception as e:
            if "already registered" in str(e):
                logger.info(f"Storage already registered for {token}")
            else:
                raise IntentExecutionError(f"Failed to register storage: {e}")

    async def intent_deposit(self, token: str, amount: float) -> Dict[str, Any]:
        """Deposit tokens to intent contract"""
        await self.ensure_initialized()
        return await self.operations.intent_deposit(token, amount)

    async def intent_withdraw(
        self, 
        token: str, 
        amount: float, 
        destination_address: str,
        network: str = "near"
    ) -> Dict[str, Any]:
        """Withdraw tokens from intent contract"""
        await self.ensure_initialized()
        return await self.operations.intent_withdraw(
            token=token,
            amount=amount,
            destination_address=destination_address,
            network=network
        )

    async def get_intent_balances(self) -> Dict[str, str]:
        """
        Get all token balances in the intent contract
        Returns a map of token symbols to balances
        """
        await self.ensure_initialized()
        balances = {}
        for token in ASSET_MAP:
            try:
                balance = await self.account.get_balance(token)
                balances[token] = str(balance)
            except Exception as e:
                logger.warning(f"Failed to get balance for {token}: {e}")
                balances[token] = "0"
        return balances
        
    async def get_quotes(self, token_in: str, amount_in: float, token_out: str) -> List[Dict]:
        """Get quotes for a token swap without executing"""
        await self.ensure_initialized()
        return await self.operations.get_quotes(
            token_in=token_in,
            amount_in=amount_in,
            token_out=token_out
        )