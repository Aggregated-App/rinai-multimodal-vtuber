"""
NEAR Intents Manager Service
Coordinates NEAR operations and key management
"""

import logging
import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from ..clients.near_intents_client import NearIntentsClient

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class NearIntentsManager:
    """Manager for NEAR Intent clients"""
    
    def __init__(self):
        self.clients: Dict[str, NearIntentsClient] = {}

    async def get_client(self, user_id: str) -> Optional[NearIntentsClient]:
        """Get or create client for user"""
        try:
            if user_id not in self.clients:
                # Initialize new client from environment variables
                account_id = os.getenv('NEAR_ACCOUNT_ID')
                private_key = os.getenv('NEAR_PRIVATE_KEY')
                
                if not account_id or not private_key:
                    logger.error("Missing required NEAR environment variables")
                    return None
                    
                self.clients[user_id] = NearIntentsClient(account_id, private_key)
                
            return self.clients[user_id]
            
        except Exception as e:
            logger.error(f"Error creating NEAR client: {str(e)}")
            return None
            
    async def remove_client(self, user_id: str) -> bool:
        """Remove client and clean up stored credentials"""
        try:
            if user_id in self.clients:
                # Clean up client resources
                client = self.clients[user_id]
                if hasattr(client, 'cleanup'):
                    await client.cleanup()
                    
                del self.clients[user_id]
                
            return True
            
        except Exception as e:
            logger.error(f"Error removing client for user {user_id}: {e}")
            return False
            
    async def cleanup(self):
        """Clean up all clients and stored credentials"""
        try:
            # Clean up all active clients
            for user_id in list(self.clients.keys()):
                await self.remove_client(user_id)
                
        except Exception as e:
            logger.error(f"Error during manager cleanup: {e}")
