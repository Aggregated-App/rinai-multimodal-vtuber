# NEAR Intents Client

A client for executing cross-chain swaps and withdrawals using NEAR Intents protocol.

## Key Parameters

### Basic Swap Parameters
- `token_in`: Input token symbol (e.g., "NEAR", "USDC")
- `amount_in`: Amount to swap
- `token_out`: Output token symbol (e.g., "USDC", "SOL")
- `chain_out`: Destination chain (e.g., "eth", "solana", "near")

### Advanced Swap Parameters
- `min_price`: Minimum price in USD for token_in (e.g., 3.5 for $3.5/NEAR)
- `monitor_interval`: How often to check quotes (in seconds)
- `max_wait_time`: Maximum time to wait for desired price (in seconds)

### Withdrawal Parameters
- `destination_chain`: Chain to withdraw to (e.g., "eth", "solana", "near")
- `destination_address`: Address to withdraw to (optional, defaults to NEAR account)

## Example Usage


