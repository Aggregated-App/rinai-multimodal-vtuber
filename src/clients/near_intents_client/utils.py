"""NEAR Intents Utility Functions"""

from typing import Optional, Dict, Any
from datetime import datetime
import base64
from borsh_construct import CStruct, String, Vec, HashMap
from decimal import Decimal

from .config import ASSET_MAP, CHAIN_IDS
from .exceptions import ValidationError, ChainSupportError, TokenSupportError

def get_asset_id(token: str) -> str:
    """Format token ID for intent protocol"""
    return f"nep141:{ASSET_MAP[token]['token_id']}"

def to_decimals(amount: float, decimals: int) -> str:
    """Convert amount to token decimals"""
    return str(int(amount * 10 ** decimals))

def from_decimals(amount: str, decimals: int) -> float:
    """Convert token decimals to human-readable amount"""
    if amount is None:
        return None
    return float(amount) / 10 ** decimals

def validate_chain_support(chain: str) -> None:
    """Validate chain is supported"""
    if chain not in CHAIN_IDS or not CHAIN_IDS[chain]["enabled"]:
        raise ChainSupportError(
            chain,
            [c for c in CHAIN_IDS if CHAIN_IDS[c]["enabled"]]
        )

def validate_token_support(token: str, chain: str) -> None:
    """Validate token is supported on chain"""
    if token not in ASSET_MAP:
        raise TokenSupportError(token, chain)
    if chain not in ASSET_MAP[token]['chains']:
        raise TokenSupportError(token, chain)

def format_response(
    status: str,
    operation: str,
    input_data: Dict[str, Any],
    output_data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    tx_hash: Optional[str] = None
) -> Dict[str, Any]:
    """Format standardized operation response"""
    return {
        "status": status,
        "operation": operation,
        "transaction_hash": tx_hash,
        "input": input_data,
        "output": output_data,
        "error": error,
        "timestamp": datetime.utcnow().isoformat()
    }

def quote_to_borsh(quote: Dict[str, Any]) -> bytes:
    """Convert quote to Borsh format for signing"""
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

def format_token_diff(token: str, amount: str, is_negative: bool = False) -> Dict[str, str]:
    """Format token diff for intent"""
    asset_id = get_asset_id(token)
    amount_str = f"-{amount}" if is_negative else amount
    return {asset_id: amount_str}

def validate_quote(quote: Dict[str, Any]) -> bool:
    """Validate quote format"""
    required_fields = [
        "quote_hash",
        "token_in",
        "token_out",
        "amount_in",
        "amount_out",
        "rate",
        "chain_id"
    ]
    
    return all(field in quote for field in required_fields)
