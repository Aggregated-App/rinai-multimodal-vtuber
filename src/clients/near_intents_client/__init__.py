"""NEAR Intents Client Package"""

import logging
from typing import List

from .client import NearIntentsClient
from .account import IntentAccount
from .intent import (
    IntentRequest,
    Intent,
    Quote,
    SignedIntent,
    IntentQuote
)
from .types import (
    PublishIntent,
    IntentResponse,
    IntentStatus,
    NearIntentsParameters
)
from .exceptions import (
    NearIntentsError,
    NearConnectionError,
    IntentExecutionError,
    ValidationError,
    ChainSupportError,
    TokenSupportError
)

logger = logging.getLogger(__name__)

__version__ = "0.1.0"

SUPPORTED_FEATURES = {
    "operations": [
        "swap",
        "deposit",
        "withdraw",
        "cross_chain_swap",
        "cross_chain_transfer"
    ],
    "chains": ["near", "eth", "aurora"],
    "tokens": ["USDC", "NEAR", "ETH", "WBTC"]
}

__all__ = [
    "NearIntentsClient",
    "IntentAccount",
    "IntentRequest",
    "Intent",
    "Quote",
    "SignedIntent",
    "IntentQuote",
    "PublishIntent",
    "IntentResponse",
    "IntentStatus",
    "NearIntentsParameters",
    "NearIntentsError",
    "NearConnectionError",
    "IntentExecutionError",
    "ValidationError",
    "ChainSupportError",
    "TokenSupportError",
    "SUPPORTED_FEATURES"
]
