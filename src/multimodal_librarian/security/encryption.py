"""
Encryption service for data at rest and in transit.

This module provides encryption/decryption functionality for sensitive data
including user content, conversations, and system data.
"""

import os
import base64
import hashlib
from typing import Union, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import secrets

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data."""
    
    def __init__(self):
        """Initialize encryption service with keys from configuration."""
        self.settings = get_settings()
        self._fernet_key = self._get_or_create_fernet_key()
        self._fernet = Fernet(self._fernet_key)
        
    def _get_or_create_fernet_key(self) -> bytes:
        """Get or create Fernet encryption key."""
        # In production, this should be stored securely (e.g., AWS KMS, HashiCorp Vault)
        key_env = os.getenv('ENCRYPTION_KEY')
        if key_env:
            try:
                return base64.urlsafe_b64decode(key_env.encode())
            except Exception as e:
                logger.warning(f"Invalid encryption key in environment: {e}")
        
        # Generate key from secret key with salt
        password = self.settings.secret_key.encode()
        salt = b'multimodal_librarian_salt'  # In production, use random salt per installation
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password))
        logger.info("Generated encryption key from secret key")
        return key
    
    def encrypt_text(self, plaintext: str) -> str:
        """Encrypt text data."""
        try:
            if not plaintext:
                return plaintext
            
            encrypted_bytes = self._fernet.encrypt(plaintext.encode('utf-8'))
            encrypted_text = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
            
            logger.debug("Text data encrypted successfully")
            return encrypted_text
            
        except Exception as e:
            logger.error(f"Failed to encrypt text: {e}")
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt_text(self, encrypted_text: str) -> str:
        """Decrypt text data."""
        try:
            if not encrypted_text:
                return encrypted_text
            
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_text.encode('utf-8'))
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            plaintext = decrypted_bytes.decode('utf-8')
            
            logger.debug("Text data decrypted successfully")
            return plaintext
            
        except Exception as e:
            logger.error(f"Failed to decrypt text: {e}")
            raise EncryptionError(f"Decryption failed: {e}")
    
    def encrypt_file(self, file_path: str, output_path: Optional[str] = None) -> str:
        """Encrypt file data."""
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            output_path = output_path or f"{file_path}.encrypted"
            
            with open(file_path, 'rb') as infile:
                file_data = infile.read()
            
            encrypted_data = self._fernet.encrypt(file_data)
            
            with open(output_path, 'wb') as outfile:
                outfile.write(encrypted_data)
            
            logger.info(f"File encrypted: {file_path} -> {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to encrypt file {file_path}: {e}")
            raise EncryptionError(f"File encryption failed: {e}")
    
    def decrypt_file(self, encrypted_file_path: str, output_path: Optional[str] = None) -> str:
        """Decrypt file data."""
        try:
            if not os.path.exists(encrypted_file_path):
                raise FileNotFoundError(f"Encrypted file not found: {encrypted_file_path}")
            
            output_path = output_path or encrypted_file_path.replace('.encrypted', '')
            
            with open(encrypted_file_path, 'rb') as infile:
                encrypted_data = infile.read()
            
            decrypted_data = self._fernet.decrypt(encrypted_data)
            
            with open(output_path, 'wb') as outfile:
                outfile.write(decrypted_data)
            
            logger.info(f"File decrypted: {encrypted_file_path} -> {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to decrypt file {encrypted_file_path}: {e}")
            raise EncryptionError(f"File decryption failed: {e}")
    
    def hash_password(self, password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """Hash password with salt for secure storage."""
        try:
            if salt is None:
                salt = secrets.token_bytes(32)
            
            # Use PBKDF2 for password hashing
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend()
            )
            
            password_hash = kdf.derive(password.encode('utf-8'))
            
            # Return base64 encoded hash and salt
            hash_b64 = base64.urlsafe_b64encode(password_hash).decode('utf-8')
            salt_b64 = base64.urlsafe_b64encode(salt).decode('utf-8')
            
            logger.debug("Password hashed successfully")
            return hash_b64, salt_b64
            
        except Exception as e:
            logger.error(f"Failed to hash password: {e}")
            raise EncryptionError(f"Password hashing failed: {e}")
    
    def verify_password(self, password: str, stored_hash: str, stored_salt: str) -> bool:
        """Verify password against stored hash."""
        try:
            salt = base64.urlsafe_b64decode(stored_salt.encode('utf-8'))
            expected_hash = base64.urlsafe_b64decode(stored_hash.encode('utf-8'))
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend()
            )
            
            try:
                kdf.verify(password.encode('utf-8'), expected_hash)
                logger.debug("Password verification successful")
                return True
            except Exception:
                logger.debug("Password verification failed")
                return False
                
        except Exception as e:
            logger.error(f"Failed to verify password: {e}")
            return False
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate cryptographically secure random token."""
        try:
            token_bytes = secrets.token_bytes(length)
            token = base64.urlsafe_b64encode(token_bytes).decode('utf-8')
            
            logger.debug(f"Generated secure token of length {length}")
            return token
            
        except Exception as e:
            logger.error(f"Failed to generate secure token: {e}")
            raise EncryptionError(f"Token generation failed: {e}")
    
    def encrypt_sensitive_fields(self, data: dict, sensitive_fields: list[str]) -> dict:
        """Encrypt specified sensitive fields in a dictionary."""
        try:
            encrypted_data = data.copy()
            
            for field in sensitive_fields:
                if field in encrypted_data and encrypted_data[field]:
                    if isinstance(encrypted_data[field], str):
                        encrypted_data[field] = self.encrypt_text(encrypted_data[field])
                    elif isinstance(encrypted_data[field], dict):
                        # Recursively encrypt nested dictionaries
                        encrypted_data[field] = self.encrypt_sensitive_fields(
                            encrypted_data[field], 
                            list(encrypted_data[field].keys())
                        )
            
            logger.debug(f"Encrypted {len(sensitive_fields)} sensitive fields")
            return encrypted_data
            
        except Exception as e:
            logger.error(f"Failed to encrypt sensitive fields: {e}")
            raise EncryptionError(f"Field encryption failed: {e}")
    
    def decrypt_sensitive_fields(self, data: dict, sensitive_fields: list[str]) -> dict:
        """Decrypt specified sensitive fields in a dictionary."""
        try:
            decrypted_data = data.copy()
            
            for field in sensitive_fields:
                if field in decrypted_data and decrypted_data[field]:
                    if isinstance(decrypted_data[field], str):
                        decrypted_data[field] = self.decrypt_text(decrypted_data[field])
                    elif isinstance(decrypted_data[field], dict):
                        # Recursively decrypt nested dictionaries
                        decrypted_data[field] = self.decrypt_sensitive_fields(
                            decrypted_data[field], 
                            list(decrypted_data[field].keys())
                        )
            
            logger.debug(f"Decrypted {len(sensitive_fields)} sensitive fields")
            return decrypted_data
            
        except Exception as e:
            logger.error(f"Failed to decrypt sensitive fields: {e}")
            raise EncryptionError(f"Field decryption failed: {e}")


class EncryptionError(Exception):
    """Exception raised for encryption/decryption errors."""
    pass


# Global encryption service instance
_encryption_service = None


def get_encryption_service() -> EncryptionService:
    """Get global encryption service instance."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service