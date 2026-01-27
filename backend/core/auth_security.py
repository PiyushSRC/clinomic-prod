"""Authentication & Security Module for Clinomic Platform.

This module provides:
- JWT access and refresh token management
- Password hashing with bcrypt
- Token fingerprinting for secure storage
- Integration with SecretsManager for key management
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(password, password_hash)


def utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


def sha256_text(text: str) -> str:
    """Compute SHA256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class TokenPair:
    """Represents an access/refresh token pair."""

    access_token: str
    refresh_token: str


def _get_jwt_config() -> tuple:
    """Get JWT configuration from settings."""
    from core.settings import settings

    return settings.jwt_secret_key, settings.jwt_algorithm


def create_access_token(payload: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    """Create a JWT access token.

    Args:
        payload: Token payload (sub, role, org_id, etc.)
        expires_minutes: Optional override for expiration time

    Returns:
        Encoded JWT access token
    """
    from core.settings import settings

    secret_key, algorithm = _get_jwt_config()
    exp_minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes

    to_encode = dict(payload)
    to_encode.update(
        {
            "token_type": "access",
            "jti": str(uuid.uuid4()),
            "iat": int(utcnow().timestamp()),
            "exp": int((utcnow() + timedelta(minutes=exp_minutes)).timestamp()),
        }
    )

    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def create_refresh_token(payload: Dict[str, Any], expires_days: Optional[int] = None) -> str:
    """Create a JWT refresh token.

    Args:
        payload: Token payload (sub, role, org_id, etc.)
        expires_days: Optional override for expiration time

    Returns:
        Encoded JWT refresh token
    """
    from core.settings import settings

    secret_key, algorithm = _get_jwt_config()
    exp_days = expires_days if expires_days is not None else settings.refresh_token_expire_days

    to_encode = dict(payload)
    to_encode.update(
        {
            "token_type": "refresh",
            "jti": str(uuid.uuid4()),
            "iat": int(utcnow().timestamp()),
            "exp": int((utcnow() + timedelta(days=exp_days)).timestamp()),
        }
    )

    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def create_mfa_pending_token(payload: Dict[str, Any], expires_minutes: int = 5) -> str:
    """Create a short-lived token for MFA verification step.

    This token is issued after password verification but before MFA,
    and can only be exchanged for full tokens after MFA verification.

    Args:
        payload: Token payload
        expires_minutes: Token expiration (default 5 minutes)

    Returns:
        Encoded JWT MFA pending token
    """
    secret_key, algorithm = _get_jwt_config()

    to_encode = dict(payload)
    to_encode.update(
        {
            "token_type": "mfa_pending",
            "jti": str(uuid.uuid4()),
            "iat": int(utcnow().timestamp()),
            "exp": int((utcnow() + timedelta(minutes=expires_minutes)).timestamp()),
        }
    )

    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: Encoded JWT token

    Returns:
        Decoded token payload

    Raises:
        JWTError: If token is invalid or expired
    """
    secret_key, algorithm = _get_jwt_config()

    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError as e:
        raise e


def refresh_token_fingerprint(token: str) -> str:
    """Create a fingerprint hash of a refresh token.

    This is used to store refresh tokens securely - only the hash
    is stored, reducing blast radius if database is compromised.

    Args:
        token: The refresh token

    Returns:
        SHA256 hash of the token
    """
    return sha256_text(token)


def create_token_pair(
    user_id: str,
    role: str,
    org_id: str,
    is_super_admin: bool = False,
    device_id: Optional[str] = None,
    mfa_verified: bool = False,
) -> TokenPair:
    """Create a complete access/refresh token pair.

    Args:
        user_id: User identifier
        role: User role
        org_id: Organization ID
        is_super_admin: Whether user is super admin
        device_id: Optional device identifier for session binding
        mfa_verified: Whether MFA has been verified

    Returns:
        TokenPair with access and refresh tokens
    """
    payload = {
        "sub": user_id,
        "role": role,
        "org_id": org_id,
        "is_super_admin": is_super_admin,
        "mfa_verified": mfa_verified,
    }

    if device_id:
        payload["device_id"] = device_id

    return TokenPair(access_token=create_access_token(payload), refresh_token=create_refresh_token(payload))


def validate_token_type(payload: Dict[str, Any], expected_type: str) -> bool:
    """Validate that a token is of the expected type.

    Args:
        payload: Decoded token payload
        expected_type: Expected token type ('access', 'refresh', 'mfa_pending')

    Returns:
        True if token type matches
    """
    token_type = payload.get("token_type")

    # Backwards compatibility: tokens without token_type are treated as access tokens
    if token_type is None and expected_type == "access":
        return True

    return token_type == expected_type
