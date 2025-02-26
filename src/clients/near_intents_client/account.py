from typing import Dict, Any, Union
import json
import base58
import logging
from decimal import Decimal
import base64
import asyncio
from near_api.providers import JsonProvider
from near_api.signer import KeyPair, Signer
from near_api.account import Account
from .exceptions import IntentExecutionError
from .config import ASSET_MAP

logger = logging.getLogger(__name__)

class IntentAccount:
    """NEAR Account implementation for Intent operations"""
    
    def __init__(self, account_id: str, private_key: str, rpc_url: str):
        self.account_id = account_id
        # Create provider
        self.provider = JsonProvider(rpc_url)
        # Create key pair and signer
        self.key_pair = KeyPair(private_key)
        self.signer = Signer(account_id, self.key_pair)
        # Create near account
        self.near_account = Account(self.provider, self.signer, account_id)
        # Store public key in both bytes and string format
        self.public_key = self.signer.public_key
        self.public_key_str = base58.b58encode(self.public_key).decode('utf-8')
        self.rpc_url = rpc_url

    @classmethod
    async def from_credentials(cls, rpc_url: str, credentials: Dict[str, Any]):
        """Create account from stored credentials"""
        return cls(
            account_id=credentials['account_id'],
            private_key=credentials['private_key'],
            rpc_url=rpc_url
        )

    def sign(self, message: bytes) -> bytes:
        """Sign a message using the account's private key"""
        return self.signer.sign(message)

    async def function_call(self, contract_id: str, method_name: str, args: Dict, gas: int, deposit: Union[int, str]) -> Dict:
        """Execute a function call on a NEAR contract"""
        try:
            if isinstance(deposit, str):
                deposit = int(deposit)
            
            args = self._prepare_args(args)
            return self.near_account.function_call(
                contract_id,
                method_name,
                args,
                gas,
                deposit
            )
        except Exception as e:
            logger.error(f"Function call failed: {e}")
            raise IntentExecutionError(f"Function call failed: {str(e)}")

    def _prepare_args(self, args: Dict) -> Dict:
        """Prepare arguments for JSON serialization"""
        processed_args = {}
        for key, value in args.items():
            if isinstance(value, bytes):
                processed_args[key] = base58.b58encode(value).decode('utf-8')
            else:
                processed_args[key] = value
        return processed_args

    async def view_function(self, contract_id: str, method_name: str, args: dict = None):
        """Call view function on contract"""
        try:
            # Convert dict to JSON string then to bytes
            args_bytes = json.dumps(args or {}).encode('utf-8')
            
            result = self.provider.view_call(
                contract_id,
                method_name,
                args_bytes
            )
            
            # Handle different result types
            if isinstance(result, dict):
                if 'result' in result:
                    try:
                        result_bytes = base64.b64decode(result['result'])
                        return json.loads(result_bytes)
                    except (TypeError, ValueError):
                        return result['result']
            return result
            
        except Exception as e:
            logger.error(f"View function failed for {contract_id}.{method_name}: {e}")
            logger.error(f"Args were: {args}")
            raise ValueError(f"Failed to call {method_name} on {contract_id}: {str(e)}")

    async def get_balance(self, token_id: str = None) -> Decimal:
        """Get account balance for token"""
        try:
            if token_id.lower() == 'near':
                account_info = self.provider.query({
                    "request_type": "view_account",
                    "account_id": self.account_id,
                    "finality": "final"
                })
                return Decimal(str(account_info['amount'])) / Decimal('1e24')
            
            result = await self.view_function(
                ASSET_MAP[token_id]['token_id'],
                'ft_balance_of',
                {'account_id': self.account_id}
            )
            
            if result and isinstance(result, (int, str)):
                balance = Decimal(str(result))
                return balance / Decimal(str(10 ** ASSET_MAP[token_id]['decimals']))
            return Decimal('0')
            
        except Exception as e:
            logger.error(f"Error getting balance for {token_id}: {e}")
            raise IntentExecutionError(f"Failed to get balance for {token_id}: {str(e)}")