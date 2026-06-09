"""
IBM Bob - Secrets Management
Secure handling and encryption of sensitive data
"""

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from bob.config import get_settings
from bob.exceptions import EncryptionError

settings = get_settings()


class SecretsManager:
    """Manages encryption and decryption of secrets"""

    def __init__(self, encryption_key: Optional[bytes] = None):
        """
        Initialize secrets manager.
        
        Args:
            encryption_key: Fernet encryption key (32 bytes, base64-encoded)
                          If not provided, uses ENCRYPTION_KEY from settings
        """
        if encryption_key is None:
            if not settings.encryption_key:
                raise EncryptionError(
                    "Encryption key not configured. Set ENCRYPTION_KEY environment variable."
                )
            encryption_key = settings.encryption_key.encode()

        try:
            self.fernet = Fernet(encryption_key)
        except Exception as e:
            raise EncryptionError(f"Invalid encryption key: {str(e)}")

    def encrypt_secret(self, plaintext: str) -> str:
        """
        Encrypt a secret value.
        
        Args:
            plaintext: Secret value to encrypt
            
        Returns:
            Base64-encoded encrypted value
            
        Raises:
            EncryptionError: If encryption fails
        """
        try:
            encrypted = self.fernet.encrypt(plaintext.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            raise EncryptionError(f"Failed to encrypt secret: {str(e)}")

    def decrypt_secret(self, ciphertext: str) -> str:
        """
        Decrypt a secret value.
        
        Args:
            ciphertext: Base64-encoded encrypted value
            
        Returns:
            Decrypted plaintext value
            
        Raises:
            EncryptionError: If decryption fails
        """
        try:
            encrypted = base64.b64decode(ciphertext.encode())
            decrypted = self.fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            raise EncryptionError(f"Failed to decrypt secret: {str(e)}")

    def rotate_encryption_key(
        self,
        new_key: bytes,
        db_connection,
    ) -> int:
        """
        Rotate encryption key and re-encrypt all secrets.
        
        This is a critical operation that should be performed during maintenance.
        
        Args:
            new_key: New Fernet encryption key
            db_connection: Database connection for updating secrets
            
        Returns:
            Number of secrets re-encrypted
            
        Raises:
            EncryptionError: If rotation fails
        """
        try:
            # Create new Fernet instance with new key
            new_fernet = Fernet(new_key)

            cursor = db_connection.cursor()

            # Get all encrypted secrets from database
            cursor.execute(
                """
                SELECT key_id, hashed_secret FROM api_keys
                WHERE hashed_secret IS NOT NULL
                """
            )

            secrets = cursor.fetchall()
            count = 0

            for key_id, encrypted_secret in secrets:
                try:
                    # Decrypt with old key
                    decrypted = self.decrypt_secret(encrypted_secret)

                    # Encrypt with new key
                    new_encrypted = base64.b64encode(
                        new_fernet.encrypt(decrypted.encode())
                    ).decode()

                    # Update in database
                    cursor.execute(
                        """
                        UPDATE api_keys
                        SET hashed_secret = %s
                        WHERE key_id = %s
                        """,
                        (new_encrypted, key_id),
                    )

                    count += 1

                except Exception as e:
                    # Log error but continue with other secrets
                    print(f"Failed to rotate secret for key {key_id}: {e}")

            db_connection.commit()

            # Update instance to use new key
            self.fernet = new_fernet

            return count

        except Exception as e:
            db_connection.rollback()
            raise EncryptionError(f"Failed to rotate encryption key: {str(e)}")


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.
    
    Returns:
        Base64-encoded encryption key (suitable for ENCRYPTION_KEY env var)
    """
    key = Fernet.generate_key()
    return key.decode()


def derive_key_from_password(password: str, salt: Optional[bytes] = None) -> bytes:
    """
    Derive encryption key from password using PBKDF2.
    
    Args:
        password: Password to derive key from
        salt: Salt for key derivation (generates random if not provided)
        
    Returns:
        Derived encryption key (32 bytes, suitable for Fernet)
    """
    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )

    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """
    Mask a secret for display purposes.
    
    Args:
        secret: Secret to mask
        visible_chars: Number of characters to show at end
        
    Returns:
        Masked secret (e.g., "bob_live_****abc123")
    """
    if len(secret) <= visible_chars:
        return "*" * len(secret)

    visible = secret[-visible_chars:]
    masked_length = len(secret) - visible_chars

    return "*" * masked_length + visible


def validate_encryption_key(key: str) -> bool:
    """
    Validate that a string is a valid Fernet encryption key.
    
    Args:
        key: Encryption key to validate
        
    Returns:
        True if valid
    """
    try:
        Fernet(key.encode())
        return True
    except Exception:
        return False


class SecretString:
    """
    Wrapper for secret strings that prevents accidental logging.
    
    Usage:
        secret = SecretString("my-secret-value")
        print(secret)  # Prints: SecretString(****)
        actual_value = secret.get_secret()  # Returns: "my-secret-value"
    """

    def __init__(self, secret: str):
        """
        Initialize secret string.
        
        Args:
            secret: Secret value
        """
        self._secret = secret

    def get_secret(self) -> str:
        """Get the actual secret value"""
        return self._secret

    def __str__(self) -> str:
        """Return masked representation"""
        return "SecretString(****)"

    def __repr__(self) -> str:
        """Return masked representation"""
        return "SecretString(****)"

    def __eq__(self, other: object) -> bool:
        """Compare secrets securely"""
        if not isinstance(other, SecretString):
            return False
        return self._secret == other._secret

    def __hash__(self) -> int:
        """Hash the secret"""
        return hash(self._secret)


# Environment variable validation
def validate_required_secrets() -> None:
    """
    Validate that all required secrets are configured.
    
    Raises:
        EncryptionError: If required secrets are missing
    """
    required_secrets = [
        "JWT_SECRET_KEY",
        "ENCRYPTION_KEY",
    ]

    missing = []

    for secret in required_secrets:
        value = os.getenv(secret)
        if not value or value == "your-secret-key-change-in-production":
            missing.append(secret)

    if missing:
        raise EncryptionError(
            f"Missing or invalid required secrets: {', '.join(missing)}. "
            "These must be set in production."
        )


def sanitize_for_logging(data: dict) -> dict:
    """
    Sanitize dictionary for logging by masking sensitive fields.
    
    Args:
        data: Dictionary to sanitize
        
    Returns:
        Sanitized dictionary with secrets masked
    """
    sensitive_keys = {
        "password",
        "secret",
        "token",
        "api_key",
        "private_key",
        "access_token",
        "refresh_token",
        "authorization",
    }

    sanitized = {}

    for key, value in data.items():
        key_lower = key.lower()

        # Check if key contains sensitive terms
        if any(term in key_lower for term in sensitive_keys):
            sanitized[key] = "****"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_for_logging(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_for_logging(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


# Made with Bob