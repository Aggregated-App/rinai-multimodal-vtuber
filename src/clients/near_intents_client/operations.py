import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import base64
import random
import json
from .exceptions import IntentExecutionError, ValidationError
from .intent import IntentRequest, IntentQuote, IntentStatus, Quote, Intent, PublishIntent
from .config import ASSET_MAP, SOLVER_BUS_URL, MAX_GAS, CHAIN_IDS, INTENT_CONTRACT
from .utils import get_asset_id, to_decimals
import aiohttp
import base58

logger = logging.getLogger(__name__)

class IntentOperations:
    """Operations for NEAR Intents protocol"""
    
    def __init__(self, client):
        self.client = client
        
    # Core Intent Operations
    async def intent_deposit(self, token: str, amount: float) -> Dict[str, Any]:
        """Deposit tokens to intent contract"""
        try:
            if amount <= 0:
                raise ValidationError("Amount must be greater than 0")
                
            # Register storage if needed
            await self.client.register_token_storage(token)
            
            deposit_amount = str(to_decimals(amount, ASSET_MAP[token]['decimals']))
            logger.info(f"Depositing {amount} {token} ({deposit_amount} decimals)")
            
            if token == "NEAR":
                # Wrap NEAR first
                await self.client.account.function_call(
                    "wrap.near",
                    "near_deposit",
                    {},
                    MAX_GAS,
                    int(deposit_amount)
                )
                
                # Transfer wrapped NEAR
                return await self.client.account.function_call(
                    "wrap.near",
                    'ft_transfer_call',
                    {
                        "receiver_id": "intents.near",
                        "amount": deposit_amount,
                        "msg": ""
                    },
                    MAX_GAS,
                    1  # 1 yoctoNEAR for ft_transfer_call
                )
            else:
                # Transfer other tokens directly
                return await self.client.account.function_call(
                    ASSET_MAP[token]['token_id'],
                    'ft_transfer_call',
                    {
                        "receiver_id": "intents.near",
                        "amount": deposit_amount,
                        "msg": ""
                    },
                    MAX_GAS,
                    1  # 1 yoctoNEAR for ft_transfer_call
                )
            
        except Exception as e:
            logger.error(f"Deposit failed: {e}")
            raise IntentExecutionError(f"Failed to deposit {amount} {token}: {str(e)}")
            
    async def get_intent_balances(self) -> Dict[str, str]:
        """Get all token balances in the intent contract"""
        logger.info("Fetching intent balances")
        try:
            balances = {}
            for token in ASSET_MAP:
                try:
                    logger.debug(f"Fetching balance for {token}")
                    balance = await self.client.account.view_function(
                        ASSET_MAP[token]['token_id'],
                        'ft_balance_of',
                        {"account_id": "intents.near"}
                    )
                    balances[token] = str(balance)
                    logger.debug(f"Balance for {token}: {balance}")
                except Exception as e:
                    logger.error(f"Failed to get balance for {token}: {e}")
                    balances[token] = "0"
            return balances
        except Exception as e:
            logger.error(f"Failed to get intent balances: {e}")
            raise IntentExecutionError(f"Failed to get intent balances: {str(e)}")

    async def intent_withdraw(self, token: str, amount: float, destination_address: str, network: str = "near"):
        nonce = base64.b64encode(random.getrandbits(256).to_bytes(32, byteorder='big')).decode('utf-8')
        quote = {
            "signer_id": self.client.account.account_id,
            "nonce": nonce,
            "verifying_contract": "intents.near",
            "deadline": "2025-12-31T11:59:59.000Z",
            "intents": [{
                "intent": "ft_withdraw",
                "token": ASSET_MAP[token]['token_id'],
                "receiver_id": destination_address,
                "amount": str(to_decimals(amount, ASSET_MAP[token]['decimals']))
            }]
        }
        
        if network != 'near':
            quote["intents"][0].update({
                "token": ASSET_MAP[token]['omft'],
                "receiver_id": ASSET_MAP[token]['omft'],
                "memo": f"WITHDRAW_TO:{destination_address}"
            })
        
        signed_quote = {
            "standard": "raw_ed25519",
            "payload": json.dumps(quote),
            "signature": self.client.sign_quote(json.dumps(quote)),
            "public_key": f"ed25519:{self.client.account.public_key_str}"
        }
        
        return await self.publish_intent({
            "signed_data": signed_quote,
            "quote_hashes": []
        })

    async def get_quotes(self, token_in: str, amount_in: float, token_out: str) -> List[Dict]:
        """Get quotes from solver bus"""
        try:
            request = IntentRequest().asset_in(token_in, amount_in).asset_out(token_out)
            
            rpc_request = {
                "id": "dontcare",
                "jsonrpc": "2.0",
                "method": "quote",
                "params": [request.serialize()]
            }
            
            async with self.client.session.post(SOLVER_BUS_URL, json=rpc_request) as response:
                result = await response.json()
                return result.get("result", [])
                
        except Exception as e:
            logger.error(f"Failed to get quotes: {e}")
            return []

    def select_best_quote(self, quotes: List[Quote]) -> Optional[Quote]:
        """Select best quote based on output amount"""
        try:
            if not quotes:
                return None
            return max(quotes, key=lambda q: float(q['amount_out']))
        except Exception as e:
            logger.error(f"Failed to select best quote: {e}")
            return None

    async def publish_intent(self, intent: Dict) -> Dict[str, Any]:
        """Publish intent to solver bus"""
        try:
            request_data = {
                "jsonrpc": "2.0",
                "id": "dontcare",
                "method": "publish_intent",
                "params": [{
                    "signed_data": intent["signed_data"],  # Access as dict
                    "quote_hashes": intent["quote_hashes"]
                }]
            }
            logger.debug(f"Publish intent request: {json.dumps(request_data, indent=2)}")
            
            async with self.client.session.post(
                SOLVER_BUS_URL,
                headers={"Content-Type": "application/json"},
                json=request_data
            ) as response:
                text = await response.text()
                logger.debug(f"Raw response text: {text}")
                
                if response.status != 200:
                    raise IntentExecutionError(f"Intent publication failed with status {response.status}: {text}")
                    
                result = json.loads(text)
                if 'error' in result:
                    raise IntentExecutionError(f"Intent publication error: {result['error']}")
                    
                return result.get('result', {})
                
        except Exception as e:
            logger.error(f"Failed to publish intent: {e}")
            raise IntentExecutionError(f"Failed to publish intent: {str(e)}")

    async def swap(self, token_in: str, amount_in: float, token_out: str, slippage: float = 0.01) -> Dict[str, Any]:
        try:
            # Input validation
            if token_in not in ASSET_MAP:
                raise ValidationError(f"Unsupported input token: {token_in}")
            if token_out not in ASSET_MAP:
                raise ValidationError(f"Unsupported output token: {token_out}")
            if amount_in <= 0:
                raise ValidationError(f"Invalid amount: {amount_in}")
                
            # Create request exactly like the example
            request = IntentRequest().asset_in(token_in, amount_in).asset_out(token_out)
            
            # Get quotes
            quotes = await self.get_quotes(token_in, float(amount_in), token_out)
            if not quotes:
                raise IntentExecutionError("No quotes available")
                
            # Select best quote
            best_quote = self.select_best_quote(quotes)
            if not best_quote:
                raise IntentExecutionError("Could not select best quote")
                
            # Create token diff quote like the example
            amount_in_decimals = to_decimals(amount_in, ASSET_MAP[token_in]['decimals'])
            quote = create_token_diff_quote(
                self.client.account,
                token_in,
                amount_in_decimals,
                token_out,
                best_quote['amount_out']
            )
            
            # Create and publish intent
            signed_intent = PublishIntent(signed_data=quote, quote_hashes=[best_quote['quote_hash']])
            response = await self.publish_intent(signed_intent)
            
            return {
                "status": "success",
                "quote": best_quote,
                "transaction": response
            }
                
        except Exception as e:
            logger.error(f"Swap execution failed: {e}")
            raise IntentExecutionError(f"Failed to swap {token_in} to {token_out}: {str(e)}")

    def _create_token_diff_intent(
        self, 
        token_in: str,
        amount_in: str,
        token_out: str,
        amount_out: str,
        quote_hash: str
    ) -> Dict:
        """Create token diff intent from quote data"""
        nonce = base64.b64encode(random.getrandbits(256).to_bytes(32, byteorder='big')).decode('utf-8')
        
        quote = {
            "signer_id": self.client.account.account_id,
            "nonce": nonce,
            "verifying_contract": "intents.near",
            "deadline": "2025-12-31T11:59:59.000Z",
            "intents": [{
                "intent": "token_diff",
                "diff": {
                    token_in: f"-{amount_in}", 
                    token_out: amount_out
                }
            }]
        }
        
        signed_quote = {
            "standard": "raw_ed25519",
            "payload": json.dumps(quote),
            "signature": self.client.sign_quote(json.dumps(quote)),
            "public_key": f"ed25519:{self.client.account.public_key_str}"
        }
        
        return {
            "signed_data": signed_quote,
            "quote_hashes": [quote_hash]
        }