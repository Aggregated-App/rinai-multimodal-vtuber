"""NEAR Intents Type Definitions"""

from typing import Dict, List, Optional, Any, TypedDict

class Quote(TypedDict):
    """Quote response from solver"""
    quote_hash: str
    defuse_asset_identifier_in: str
    defuse_asset_identifier_out: str
    amount_in: str
    amount_out: str
    expiration_time: int

class Intent(TypedDict):
    """Intent definition for token operations"""
    intent: str  # "token_diff" | "ft_withdraw"
    diff: Dict[str, str]  # For token_diff
    token: Optional[str]  # For ft_withdraw
    receiver_id: Optional[str]  # For ft_withdraw
    amount: Optional[str]  # For ft_withdraw
    memo: Optional[str]  # For cross-chain ft_withdraw

class SignedIntent(TypedDict):
    """Signed intent for publishing"""
    standard: str  # "raw_ed25519"
    payload: str  # JSON string of intent
    signature: str
    public_key: str

class PublishIntent(TypedDict):
    """Intent publication request"""
    signed_data: SignedIntent
    quote_hashes: List[str]

class IntentStatus(TypedDict):
    """Intent status response"""
    status: str  # "pending" | "completed" | "failed"
    transaction_hash: Optional[str]
    error: Optional[str]
    completion_time: Optional[str]

class IntentResponse(TypedDict):
    status: str
    operation_type: str
    transaction_hash: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    error: str

class NearIntentsParameters(TypedDict):
    """Parameters for NEAR Intent operations"""
    operation: str
    token_in: str
    amount_in: float
    token_out: Optional[str] = None
    destination_address: Optional[str] = None
    destination_chain: Optional[str] = None
    slippage_tolerance: Optional[float] = 0.01
