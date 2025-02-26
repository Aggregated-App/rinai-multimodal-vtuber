from typing import List, Dict, Any, Optional, TypedDict
from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from .config import ASSET_MAP
from .utils import get_asset_id, to_decimals
from .exceptions import ValidationError

class IntentRequest:
    """Request for intent protocol operations"""
    
    def __init__(self, min_deadline_ms: int = 120000):
        self.min_deadline_ms = min_deadline_ms
        self.asset_in = None
        self.asset_out = None

    def asset_in(self, asset_name: str, amount: float) -> 'IntentRequest':
        """Set input asset"""
        self.asset_in = {
            "asset": get_asset_id(asset_name),
            "amount": to_decimals(amount, ASSET_MAP[asset_name]['decimals'])
        }
        return self

    def asset_out(self, asset_name: str, amount: Optional[float] = None) -> 'IntentRequest':
        """Set output asset"""
        self.asset_out = {
            "asset": get_asset_id(asset_name),
            "amount": to_decimals(amount, ASSET_MAP[asset_name]['decimals']) if amount else None
        }
        return self

    def serialize(self) -> Dict[str, Any]:
        """Serialize request for solver"""
        if not self.asset_in or not self.asset_out:
            raise ValueError("Both asset_in and asset_out must be set")
            
        message = {
            "defuse_asset_identifier_in": self.asset_in["asset"],
            "defuse_asset_identifier_out": self.asset_out["asset"],
            "exact_amount_in": str(self.asset_in["amount"]),
            "exact_amount_out": str(self.asset_out["amount"]) if self.asset_out["amount"] else None,
            "min_deadline_ms": self.min_deadline_ms,
        }
        
        if self.asset_in["amount"] is None:
            del message["exact_amount_in"]
        if self.asset_out["amount"] is None:
            del message["exact_amount_out"]
            
        return message

class Intent(TypedDict):
    intent: str
    diff: Dict[str, str]

class Quote(BaseModel):
    """Quote model for solver responses"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    quote_hash: str
    token_in: str
    token_out: str
    amount_in: str
    amount_out: str
    rate: str
    chain_id: str = "near"
    exact_in: bool = True

class IntentQuote(BaseModel):
    """Intent quote model"""
    signer_id: str
    nonce: str
    verifying_contract: str
    deadline: str
    intents: List[Intent]

class PublishIntent(BaseModel):
    """Model for publishing intents"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    signed_data: str
    quote_hashes: List[str]

    def dict(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "signed_data": self.signed_data,
            "quote_hashes": self.quote_hashes
        }

class IntentStatus(BaseModel):
    """Intent status model"""
    status: str
    hash: str
    timestamp: str

class Commitment(BaseModel):
    """Commitment model"""
    commitment_id: str
    solver_id: str
    intent_hash: str
    status: str
    timestamp: str

class SignedIntent(BaseModel):
    """Signed intent model with commitment data"""
    signed: List[Commitment]
    quote_hashes: List[str] = []

    def dict(self, *args, **kwargs) -> Dict[str, Any]:
        return {
            "signed": self.signed,
            "quote_hashes": self.quote_hashes
        }