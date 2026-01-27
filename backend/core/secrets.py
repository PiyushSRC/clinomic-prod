"""Secrets Management Module for Clinomic Platform.

This module provides secure secrets management with:
- Environment-based secret loading (required for production)
- Automatic secure key generation for development/demo
- Key rotation support
- Validation to prevent hardcoded secrets in production
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from cryptography.fernet import Fernet

logger = logging.getLogger("clinomic.secrets")


class SecretsValidationError(Exception):
    """Raised when secrets validation fails."""

    pass


@dataclass
class SecretKey:
    """Represents a secret key with metadata."""

    value: str
    key_id: str
    created_at: str
    source: str  # 'env', 'generated', 'vault'
    is_rotated: bool = False


class SecretsManager:
    """
    Centralized secrets management for the Clinomic platform.

    In production mode:
    - All secrets MUST be provided via environment variables
    - No fallback keys are allowed
    - Validation is strict

    In development/demo mode:
    - Secure random keys are generated if not provided
    - Keys are logged for debugging (but not the actual values)
    """

    REQUIRED_SECRETS = [
        "JWT_SECRET_KEY",
        "MASTER_ENCRYPTION_KEY",
        "AUDIT_SIGNING_KEY",
    ]

    def __init__(self, app_env: str = "dev"):
        self.app_env = app_env
        self._secrets: Dict[str, SecretKey] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Initialize all required secrets."""
        if self._initialized:
            return

        logger.info(f"Initializing secrets manager for environment: {self.app_env}")

        # Load JWT Secret
        self._secrets["JWT_SECRET_KEY"] = self._load_secret(
            "JWT_SECRET_KEY", min_length=32, generator=lambda: secrets.token_urlsafe(64)
        )

        # Load Master Encryption Key (must be valid Fernet key)
        self._secrets["MASTER_ENCRYPTION_KEY"] = self._load_secret(
            "MASTER_ENCRYPTION_KEY",
            min_length=32,
            generator=lambda: Fernet.generate_key().decode(),
            validator=self._validate_fernet_key,
        )

        # Load Audit Signing Key
        self._secrets["AUDIT_SIGNING_KEY"] = self._load_secret(
            "AUDIT_SIGNING_KEY", min_length=32, generator=lambda: secrets.token_hex(64)
        )

        # Validate in production
        if self.app_env == "prod":
            self._validate_production_secrets()

        self._initialized = True
        logger.info(f"Secrets manager initialized with {len(self._secrets)} secrets")

    def _load_secret(
        self, name: str, min_length: int = 32, generator: Optional[callable] = None, validator: Optional[callable] = None
    ) -> SecretKey:
        """Load a secret from environment or generate if in dev mode."""
        env_value = os.environ.get(name)

        if env_value:
            # Validate minimum length
            if len(env_value) < min_length:
                raise SecretsValidationError(f"Secret {name} must be at least {min_length} characters")
            # Run custom validator if provided
            if validator and not validator(env_value):
                raise SecretsValidationError(f"Secret {name} failed validation")
            return SecretKey(
                value=env_value,
                key_id=self._generate_key_id(env_value),
                created_at=datetime.now(timezone.utc).isoformat(),
                source="env",
            )

        # In production, secrets are required
        if self.app_env == "prod":
            raise SecretsValidationError(f"Secret {name} is required in production environment")

        # Generate for dev/demo
        if generator:
            generated = generator()
            logger.warning(
                f"Generated secret for {name} (key_id: {self._generate_key_id(generated)[:8]}...) - "
                f"This is OK for dev/demo but NOT for production"
            )
            return SecretKey(
                value=generated,
                key_id=self._generate_key_id(generated),
                created_at=datetime.now(timezone.utc).isoformat(),
                source="generated",
            )

        raise SecretsValidationError(f"No secret found for {name} and no generator provided")

    def _generate_key_id(self, value: str) -> str:
        """Generate a non-reversible key ID for tracking."""
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    def _validate_fernet_key(self, key: str) -> bool:
        """Validate that a key is a valid Fernet key."""
        try:
            Fernet(key.encode())
            return True
        except Exception:
            return False

    def _validate_production_secrets(self) -> None:
        """Validate that all secrets meet production requirements."""
        for name in self.REQUIRED_SECRETS:
            secret = self._secrets.get(name)
            if not secret:
                raise SecretsValidationError(f"Required secret {name} not loaded")
            if secret.source == "generated":
                raise SecretsValidationError(f"Secret {name} must be provided via environment in production")
        logger.info("Production secrets validation passed")

    def get_secret(self, name: str) -> str:
        """Get a secret value by name."""
        if not self._initialized:
            self.initialize()
        secret = self._secrets.get(name)
        if not secret:
            raise SecretsValidationError(f"Secret {name} not found")
        return secret.value

    def get_secret_metadata(self, name: str) -> Dict:
        """Get secret metadata (without the actual value)."""
        if not self._initialized:
            self.initialize()
        secret = self._secrets.get(name)
        if not secret:
            return {}
        return {
            "key_id": secret.key_id,
            "created_at": secret.created_at,
            "source": secret.source,
            "is_rotated": secret.is_rotated,
        }

    def rotate_secret(self, name: str, new_value: str) -> Tuple[str, str]:
        """Rotate a secret and return (old_key_id, new_key_id)."""
        if not self._initialized:
            self.initialize()

        old_secret = self._secrets.get(name)
        old_key_id = old_secret.key_id if old_secret else None

        # Mark old secret as rotated
        if old_secret:
            old_secret.is_rotated = True

        # Create new secret
        new_secret = SecretKey(
            value=new_value,
            key_id=self._generate_key_id(new_value),
            created_at=datetime.now(timezone.utc).isoformat(),
            source="env",
        )
        self._secrets[name] = new_secret

        logger.info(f"Rotated secret {name}: {old_key_id} -> {new_secret.key_id}")
        return old_key_id, new_secret.key_id

    def get_health_status(self) -> Dict:
        """Get health status of secrets for monitoring."""
        return {
            "initialized": self._initialized,
            "environment": self.app_env,
            "secrets_loaded": len(self._secrets),
            "secrets": {
                name: {"key_id": secret.key_id[:8] + "...", "source": secret.source, "is_rotated": secret.is_rotated}
                for name, secret in self._secrets.items()
            },
        }


# Global singleton instance
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager instance."""
    global _secrets_manager
    if _secrets_manager is None:
        app_env = os.environ.get("APP_ENV", "dev")
        _secrets_manager = SecretsManager(app_env)
        _secrets_manager.initialize()
    return _secrets_manager


def get_secret(name: str) -> str:
    """Convenience function to get a secret."""
    return get_secrets_manager().get_secret(name)
