"""NEAR Intents Configuration"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

# RPC Configuration
INTENT_CONTRACT = os.getenv('INTENT_CONTRACT', 'intents.near')
SOLVER_BUS_URL = os.getenv('SOLVER_BUS_URL', 'https://solver-relay-v2.chaindefuser.com/rpc')  # Default URL
NEAR_RPC_URL = os.getenv('NEAR_RPC_URL', 'https://rpc.mainnet.near.org')
MAX_GAS = 300 * 10**12


# Chain Configuration
CHAIN_IDS = {
    "eth": {
        "id": 1,
        "name": "Ethereum",
        "enabled": True,
        "exchanges": ["uniswap_v3"]
    },
    "near": {
        "id": "near",
        "name": "NEAR Protocol",
        "enabled": True,
        "exchanges": ["ref_finance"]
    },
    "aurora": {
        "id": 1313161554,
        "name": "Aurora",
        "enabled": True,
        "exchanges": ["trisolaris"]
    }
}

# Asset Configuration
ASSET_MAP = {
    'USDC': {
        'token_id': '17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1',
        'omft': 'eth-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.omft.near',
        'decimals': 6,
        'chains': ['eth', 'near', 'aurora']
    },
    'ETH': {
        'token_id': 'aurora',
        'omft': 'eth-0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2.omft.near',
        'decimals': 18,
        'chains': ['eth', 'near', 'aurora']
    },
    'NEAR': {
        'token_id': 'wrap.near',
        'decimals': 24,
        'chains': ['near']
    }
}

# Operation Configuration
OPERATION_CONFIGS = {
    "swap": {
        "timeout": 300,  # seconds
        "poll_interval": 2,
        "max_slippage": 0.01
    },
    "cross_chain_swap": {
        "timeout": 600,  # seconds
        "poll_interval": 5,
        "max_slippage": 0.02
    }
}

MINIMUM_AMOUNTS = {
    'NEAR': 0.1,  # Minimum NEAR for gas
    'ETH': 0.001,  # Minimum ETH for gas
    'USDC': 1.0,   # Minimum USDC
}

GAS_ESTIMATES = {
    'swap': 0.01,
    'cross_chain_swap': 0.05,
    'deposit': 0.01,
    'withdraw': 0.02
}

# Add validation
if not SOLVER_BUS_URL:
    raise ValueError("SOLVER_BUS_URL must be set in environment or use default")

if not NEAR_RPC_URL:
    raise ValueError("NEAR_RPC_URL must be set in environment or use default")

if not INTENT_CONTRACT:
    raise ValueError("INTENT_CONTRACT must be set in environment or use default")
