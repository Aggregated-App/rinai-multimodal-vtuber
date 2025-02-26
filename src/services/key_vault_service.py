import base64
import json
import logging
import time
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class KeyVaultService:
    def __init__(self, encryption_key: str, salt: bytes = None):
        """Initialize key vault with encryption
        
        Args:
            encryption_key: Master key for encrypting user keys
            salt: Optional salt for key derivation
        """
        self.salt = salt or b'rinai_secure_salt'  # Should be configured per environment
        self.storage = {}  # Replace with secure database in production
        
        # Derive encryption key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
        self.fernet = Fernet(key)

    async def store_key(self, user_id: str, key_data: Dict, expiry_seconds: int = 3600) -> bool:
        """Encrypt and store key with expiration
        
        Args:
            user_id: Unique user identifier
            key_data: Dictionary containing key information
            expiry_seconds: Seconds until key expires
        """
        try:
            encrypted_data = {
                'data': self.fernet.encrypt(json.dumps(key_data).encode()),
                'expiry': int(time.time()) + expiry_seconds
            }
            self.storage[user_id] = encrypted_data
            logger.info(f"Stored encrypted key for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error storing key for user {user_id}: {e}")
            return False

    async def retrieve_key(self, user_id: str) -> Optional[Dict]:
        """Retrieve and decrypt key if not expired"""
        try:
            encrypted_data = self.storage.get(user_id)
            if not encrypted_data:
                return None

            # Check expiration
            if time.time() > encrypted_data['expiry']:
                await self.delete_key(user_id)
                return None

            # Decrypt key data
            decrypted = self.fernet.decrypt(encrypted_data['data'])
            return json.loads(decrypted)
            
        except Exception as e:
            logger.error(f"Error retrieving key for user {user_id}: {e}")
            return None

    async def delete_key(self, user_id: str) -> bool:
        """Remove key from storage"""
        try:
            if user_id in self.storage:
                del self.storage[user_id]
                logger.info(f"Deleted key for user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting key for user {user_id}: {e}")
            return False