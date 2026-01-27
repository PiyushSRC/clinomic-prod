"""Cryptography Module for Clinomic Platform.

Handles envelope encryption for PHI protection with:
- Fernet symmetric encryption
- Secure key management via SecretsManager
- Field-level encryption utilities
"""

from __future__ import annotations

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("clinomic.crypto")


class CryptoManager:
    """
    Handles envelope encryption for PHI protection.

    In production, the master key is loaded from the secrets manager.
    In development, a secure random key is generated if not provided.
    """

    def __init__(self):
        self._cipher: Optional[Fernet] = None
        self._initialized = False

    def _get_cipher(self) -> Fernet:
        """Lazy-initialize the cipher with the master key."""
        if self._cipher is None:
            from core.secrets import get_secret

            try:
                master_key = get_secret("MASTER_ENCRYPTION_KEY")
                self._cipher = Fernet(master_key.encode())
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize encryption: {e}")
                raise
        return self._cipher

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt

        Returns:
            Base64-encoded ciphertext
        """
        if not plaintext:
            return ""

        cipher = self._get_cipher()
        return cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string.

        Args:
            ciphertext: Base64-encoded ciphertext

        Returns:
            Decrypted plaintext
        """
        if not ciphertext:
            return ""

        cipher = self._get_cipher()
        try:
            return cipher.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            logger.warning("Decryption failed - invalid token or key mismatch")
            return "[DECRYPTION_FAILED]"
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return "[DECRYPTION_ERROR]"

    def encrypt_dict_field(self, data: dict, field: str) -> dict:
        """Encrypt a specific field in a dictionary.

        Args:
            data: Dictionary containing the field
            field: Field name to encrypt

        Returns:
            Dictionary with encrypted field
        """
        result = dict(data)
        if field in result and result[field]:
            result[field] = self.encrypt(str(result[field]))
        return result

    def decrypt_dict_field(self, data: dict, field: str) -> dict:
        """Decrypt a specific field in a dictionary.

        Args:
            data: Dictionary containing the encrypted field
            field: Field name to decrypt

        Returns:
            Dictionary with decrypted field
        """
        result = dict(data)
        if field in result and result[field]:
            result[field] = self.decrypt(str(result[field]))
        return result

    def is_initialized(self) -> bool:
        """Check if the crypto manager is properly initialized."""
        return self._initialized

    def get_health_status(self) -> dict:
        """Get health status for monitoring."""
        return {"initialized": self._initialized, "cipher_ready": self._cipher is not None}


# Lazy-initialized singleton
_crypto_manager: Optional[CryptoManager] = None


def get_crypto_manager() -> CryptoManager:
    """Get the global crypto manager instance."""
    global _crypto_manager
    if _crypto_manager is None:
        _crypto_manager = CryptoManager()
    return _crypto_manager


# Backwards compatibility - create a proxy that initializes lazily
class _CryptoManagerProxy:
    """Proxy for lazy initialization of CryptoManager."""

    def __getattr__(self, name):
        return getattr(get_crypto_manager(), name)


crypto_manager = _CryptoManagerProxy()
