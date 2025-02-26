"""NEAR Intents Custom Exceptions"""

class NearIntentsError(Exception):
    """Base exception for NEAR Intents"""
    pass

class NearConnectionError(NearIntentsError):
    """Error connecting to NEAR RPC or Solver Bus"""
    pass

class IntentExecutionError(NearIntentsError):
    """Error during intent execution"""
    pass

class ValidationError(NearIntentsError):
    """Error validating parameters or responses"""
    pass

class ChainSupportError(NearIntentsError):
    """Error when chain is not supported"""
    def __init__(self, chain: str, supported_chains: list):
        self.chain = chain
        self.supported_chains = supported_chains
        super().__init__(
            f"Chain {chain} not supported. Supported chains: {', '.join(supported_chains)}"
        )

class TokenSupportError(NearIntentsError):
    """Error when token is not supported"""
    def __init__(self, token: str, chain: str):
        self.token = token
        self.chain = chain
        super().__init__(
            f"Token {token} not supported on chain {chain}"
        )

class IntentTimeoutError(NearIntentsError):
    """Error when intent execution times out"""
    def __init__(self, intent_hash: str, timeout: int):
        self.intent_hash = intent_hash
        self.timeout = timeout
        super().__init__(
            f"Intent {intent_hash} timed out after {timeout} seconds"
        )
