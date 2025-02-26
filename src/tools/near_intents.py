"""NEAR Intents Tool Implementation"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

from .base import BaseTool
from ..clients.near_intents_client import ValidationError
from ..managers.near_intents_manager import NearIntentsManager

logger = logging.getLogger(__name__)

SUPPORTED_FEATURES = {
    "operations": [
        "swap",
        "deposit",
        "withdraw",
        "cross_chain_swap",
        "cross_chain_transfer"
    ]
}

class NearIntentsParameters(BaseModel):
    """Parameters for NEAR Intents operations"""
    operation: str = Field(
        description="Operation type (swap, deposit, withdraw, cross_chain_swap)",
        validator=lambda v: v in SUPPORTED_FEATURES["operations"]
    )
    token_in: str = Field(
        description="Input token symbol (e.g., 'NEAR', 'USDC')"
    )
    amount_in: float = Field(
        description="Amount of input token"
    )
    token_out: Optional[str] = Field(
        default=None,
        description="Output token symbol for swaps"
    )
    destination_address: Optional[str] = Field(
        default=None,
        pattern=r'^[a-zA-Z0-9_-]+\.near$',
        description="Destination address for transfers/withdrawals"
    )
    destination_chain: Optional[str] = Field(
        default=None,
        description="Destination chain for cross-chain operations"
    )
    slippage_tolerance: Optional[float] = Field(
        default=0.05,  # 5% default slippage
        ge=0.001,  # Min 0.1%
        le=0.1,   # Max 10%
        description="Slippage tolerance for swaps"
    )
    gas_limit: Optional[int] = Field(
        default=None,
        description="Custom gas limit for the transaction"
    )

class NearIntentsResponse(BaseModel):
    """Response structure for NEAR Intents operations"""
    status: Literal["success", "pending", "failed"]
    operation_type: str
    transaction_hash: Optional[str]
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]]
    error: Optional[str]
    timestamp: str

class NearIntentsTool(BaseTool):
    """Tool for executing NEAR Protocol Intent operations"""
    name = "near_intents"
    description = "Execute NEAR Protocol operations (swap, deposit, withdraw, cross-chain) using Intents"
    version = "0.1.0"

    def __init__(self):
        super().__init__()
        self.manager = None

    async def run(self, input_data: Any) -> Dict[str, Any]:
        """Execute the tool's main functionality"""
        return await self.execute(input_data)  # Delegate to existing execute method

    async def initialize(self):
        """Initialize NEAR Intents manager"""
        if not self.manager:
            self.manager = NearIntentsManager()

    def can_handle(self, input_data: Any) -> bool:
        """Check if this tool can handle the input"""
        try:
            if isinstance(input_data, dict):
                # Validate operation type
                if input_data.get("operation") not in SUPPORTED_FEATURES["operations"]:
                    return False
                    
                # Validate required parameters based on operation
                if input_data["operation"] in ["cross_chain_swap", "cross_chain_transfer"]:
                    required = {"token_in", "amount_in", "destination_address", "destination_chain"}
                    if not all(field in input_data for field in required):
                        return False
                        
                return True
            return False
        except Exception:
            return False

    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute NEAR Intent operation with state management"""
        try:
            # Initialize if needed
            if not self.manager:
                await self.initialize()

            # Validate parameters
            params = NearIntentsParameters(**parameters)
            
            # Check balance and get preview
            check_result = await self._check_balance_and_preview(parameters)
            if check_result["status"] != "ready":
                return check_result

            # Update operation state to executing
            if self.deps and self.deps.conversation_id:
                await self.tool_state_manager.update_operation_state(
                    session_id=self.deps.conversation_id,
                    status="executing",
                    data={"params": parameters, "check_result": check_result}
                )

            # Get client and execute operation
            client = await self.manager.get_client("default_user")
            if not client:
                raise ValueError("Failed to initialize NEAR client")

            # Execute operation based on type
            result = await self._execute_operation(client, params)

            # Update final state
            if self.deps and self.deps.conversation_id:
                await self.tool_state_manager.update_operation_state(
                    session_id=self.deps.conversation_id,
                    status="completed",
                    data=result
                )

            return result

        except Exception as e:
            return await self._handle_operation_error(e)

    async def _process_near_approval_response(self, message: str, session_id: str) -> Dict[str, Any]:
        """Handle approval response for NEAR operations"""
        try:
            # Get current operation state
            operation_state = await self.tool_state_manager.get_operation_state(session_id)
            if not operation_state:
                return {"status": "error", "message": "No pending operation found"}

            # Check if user approved
            approved = any(word in message.lower() for word in ['yes', 'confirm', 'approve', 'proceed'])
            if not approved:
                await self.tool_state_manager.end_operation(session_id)
                return {
                    "status": "cancelled",
                    "message": "Operation cancelled by user"
                }

            # Execute the operation
            params = operation_state.get("parameters", {})
            result = await self.execute(params)
            
            # Update operation state
            await self.tool_state_manager.update_operation_state(
                session_id=session_id,
                status="completed",
                data=result
            )

            return {
                "status": "success",
                "data": result,
                "response": self._format_success_message(result)
            }

        except Exception as e:
            logger.error(f"Error processing NEAR approval: {e}")
            return {"status": "error", "message": str(e)}

    def _format_success_message(self, result: Dict[str, Any]) -> str:
        """Format success message based on operation type"""
        operation = result.get("operation_type")
        if operation == "swap":
            return f"Successfully swapped {result['input']['amount']} {result['input']['token']} for {result['output']['token']}"
        elif operation == "deposit":
            return f"Successfully deposited {result['input']['amount']} {result['input']['token']}"
        elif operation == "withdraw":
            return f"Successfully withdrew {result['input']['amount']} {result['input']['token']}"
        return "Operation completed successfully"

    async def _check_balance_and_preview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check balance and generate operation preview"""
        try:
            if not self.manager:
                await self.initialize()

            client = await self.manager.get_client("default_user")
            flow_check = await client.operations.check_user_flow(
                token_in=params["token_in"],
                amount_in=params["amount_in"],
                token_out=params.get("token_out")
            )

            if flow_check["status"] == "needs_deposit":
                return {
                    "status": "needs_deposit",
                    "message": f"Insufficient balance. You need {params['amount_in']} {params['token_in']} but have {flow_check['current_balance']}",
                    "data": flow_check
                }
            elif flow_check["status"] == "needs_approval":
                return {
                    "status": "needs_approval",
                    "message": f"Approval needed for {params['amount_in']} {params['token_in']}",
                    "data": flow_check
                }

            # Generate preview message
            preview = self._generate_operation_preview(params)
            return {
                "status": "ready",
                "message": preview,
                "data": flow_check
            }

        except Exception as e:
            logger.error(f"Error in balance check: {e}")
            return {"status": "error", "message": str(e)}

    def _generate_operation_preview(self, params: Dict[str, Any]) -> str:
        """Generate human-readable preview of the operation"""
        operation = params["operation"]
        amount = params["amount_in"]
        token = params["token_in"]

        previews = {
            "swap": f"Swap {amount} {token} for {params['token_out']}",
            "deposit": f"Deposit {amount} {token}",
            "withdraw": f"Withdraw {amount} {token} to {params['destination_address']}",
            "cross_chain_swap": f"Swap {amount} {token} for {params['token_out']} on {params['destination_chain']}",
            "cross_chain_transfer": f"Transfer {amount} {token} to {params['destination_chain']}"
        }

        return f"Preview: {previews.get(operation, 'Unknown operation')}\nDo you want to proceed?"

    async def _handle_operation_error(self, error: Exception) -> Dict[str, Any]:
        """Handle operation errors with recovery options"""
        error_str = str(error)
        error_response = {
            "status": "error",
            "message": error_str,
            "recovery_options": []
        }

        # Update operation state if available
        if self.deps and self.deps.conversation_id:
            await self.tool_state_manager.update_operation_state(
                session_id=self.deps.conversation_id,
                status="error",
                data={"error": error_str}
            )

        # Handle specific error types
        if "insufficient balance" in error_str.lower():
            error_response["recovery_options"] = ["check_balance", "deposit"]
            error_response["message"] = "Insufficient balance. Would you like to check your balance or make a deposit?"
        elif "slippage" in error_str.lower():
            error_response["recovery_options"] = ["retry", "adjust_slippage"]
            error_response["message"] = "Price changed too much. Would you like to retry with updated prices?"
        elif "approval" in error_str.lower():
            error_response["recovery_options"] = ["approve"]
            error_response["message"] = "Token approval needed. Would you like to approve now?"
        
        logger.error(f"Operation error: {error_str}")
        return error_response

    async def _execute_operation(self, client, params: NearIntentsParameters) -> Dict[str, Any]:
        """Execute specific operation with error handling"""
        try:
            operations = {
                "swap": client.operations.execute_complete_flow,
                "deposit": client.operations.intent_deposit,
                "withdraw": client.operations.intent_withdraw,
                "cross_chain_swap": client.operations.cross_chain_swap,
                "cross_chain_transfer": client.operations.cross_chain_transfer
            }

            operation_func = operations.get(params.operation)
            if not operation_func:
                raise ValueError(f"Unsupported operation: {params.operation}")

            return await operation_func(**params.dict(exclude_none=True))

        except Exception as e:
            raise Exception(f"Error in {params.operation}: {str(e)}")

    async def _get_swap_quote(self, client, params: NearIntentsParameters) -> Dict[str, Any]:
        """Get and validate swap quote"""
        try:
            request = client.operations.create_intent_request(
                token_in=params.token_in,
                amount_in=params.amount_in,
                token_out=params.token_out,
                slippage=params.slippage_tolerance
            )
            
            quotes = await client.operations.get_quotes(request)
            if not quotes:
                raise ValueError("No quotes available for this swap")
                
            # Get best quote meeting requirements
            best_quote = max(quotes, key=lambda q: q.get("output_amount", 0))
            
            return {
                "status": "success",
                "quote": best_quote,
                "preview": f"Best rate: 1 {params.token_in} = {best_quote['rate']} {params.token_out}"
            }
            
        except Exception as e:
            logger.error(f"Error getting swap quote: {e}")
            raise ValueError(f"Failed to get swap quote: {str(e)}")

    async def handle_recovery_action(self, action: str, original_params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle recovery actions for failed operations"""
        try:
            if action == "check_balance":
                return await self._check_balance_and_preview(original_params)
                
            elif action == "adjust_slippage":
                # Increase slippage tolerance
                new_params = original_params.copy()
                new_params["slippage_tolerance"] = min(
                    (original_params.get("slippage_tolerance", 0.05) * 1.5),
                    0.1  # Max 10%
                )
                return await self.execute(new_params)
                
            elif action == "approve":
                client = await self.manager.get_client("default_user")
                return await client.operations.approve_token(
                    token=original_params["token_in"],
                    amount=original_params["amount_in"]
                )
                
            raise ValueError(f"Unsupported recovery action: {action}")
            
        except Exception as e:
            logger.error(f"Error in recovery action {action}: {e}")
            return {
                "status": "error",
                "message": f"Recovery action failed: {str(e)}"
            }

    async def _update_operation_progress(self, session_id: str, status: str, details: Dict[str, Any]) -> None:
        """Update operation progress with detailed state"""
        await self.tool_state_manager.update_operation_state(
            session_id=session_id,
            status=status,
            data={
                "timestamp": datetime.utcnow().isoformat(),
                "status": status,
                **details
            }
        )
