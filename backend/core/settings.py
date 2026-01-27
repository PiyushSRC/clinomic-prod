"""Application Settings for Clinomic Platform.

This module provides centralized configuration management with:
- Environment-based configuration (dev, demo, pilot, prod)
- Secure secrets loading via SecretsManager
- Validation for production deployments
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Import secrets manager - lazy initialization to avoid circular imports
_secrets_initialized = False


def _get_secret_lazy(name: str) -> str:
    """Lazy load secrets to avoid import issues."""
    # Note: _secrets_initialized is a module-level flag for lazy loading
    if not _secrets_initialized:
        return ""  # Return empty during initial load, will be populated later
    from core.secrets import get_secret

    return get_secret(name)


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    # Environment: dev | demo | pilot | staging | prod
    app_env: str = os.environ.get("APP_ENV", "dev")

    # CORS Configuration
    cors_origins: str = os.environ.get("CORS_ORIGINS", "*")

    # JWT Configuration (secrets loaded separately)
    jwt_algorithm: str = os.environ.get("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    refresh_token_expire_days: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # Multi-tenant Configuration
    default_org_id: str = os.environ.get("DEFAULT_ORG_ID", "ORG-CLINOMIC")

    # Rate Limiting
    rate_limit_enabled: bool = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"

    # MFA Configuration
    mfa_required_roles: str = os.environ.get("MFA_REQUIRED_ROLES", "ADMIN,DOCTOR")  # Comma-separated
    mfa_grace_period_hours: int = int(os.environ.get("MFA_GRACE_PERIOD_HOURS", "24"))

    # Demo Mode Configuration
    demo_mode_enabled: bool = os.environ.get("DEMO_MODE_ENABLED", "false").lower() == "true"
    demo_users_enabled: bool = os.environ.get("DEMO_USERS_ENABLED", "true").lower() == "true"

    # Feature Flags
    audit_v2_enabled: bool = os.environ.get("AUDIT_V2_ENABLED", "true").lower() == "true"
    device_tracking_enabled: bool = os.environ.get("DEVICE_TRACKING_ENABLED", "true").lower() == "true"

    @property
    def jwt_secret_key(self) -> str:
        """Get JWT secret key from secrets manager."""
        from core.secrets import get_secret

        return get_secret("JWT_SECRET_KEY")

    @property
    def master_encryption_key(self) -> str:
        """Get master encryption key from secrets manager."""
        from core.secrets import get_secret

        return get_secret("MASTER_ENCRYPTION_KEY")

    @property
    def audit_signing_key(self) -> str:
        """Get audit signing key from secrets manager."""
        from core.secrets import get_secret

        return get_secret("AUDIT_SIGNING_KEY")

    @property
    def mfa_required_role_list(self) -> list:
        """Get list of roles that require MFA."""
        return [r.strip().upper() for r in self.mfa_required_roles.split(",") if r.strip()]

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "prod"

    def is_demo(self) -> bool:
        """Check if running in demo mode."""
        return self.app_env == "demo" or self.demo_mode_enabled

    def requires_mfa(self, role: str) -> bool:
        """Check if a role requires MFA."""
        return role.upper() in self.mfa_required_role_list

    def get_config_summary(self) -> dict:
        """Get configuration summary for debugging (no secrets)."""
        return {
            "app_env": self.app_env,
            "jwt_algorithm": self.jwt_algorithm,
            "access_token_expire_minutes": self.access_token_expire_minutes,
            "refresh_token_expire_days": self.refresh_token_expire_days,
            "rate_limit_enabled": self.rate_limit_enabled,
            "mfa_required_roles": self.mfa_required_role_list,
            "demo_mode_enabled": self.demo_mode_enabled,
            "demo_users_enabled": self.demo_users_enabled,
            "audit_v2_enabled": self.audit_v2_enabled,
        }


# Global settings instance
settings = Settings()


def validate_production_config() -> None:
    """Validate configuration for production deployment."""
    if not settings.is_production():
        return

    errors = []

    # CORS must not be wildcard in production
    if settings.cors_origins == "*":
        errors.append("CORS_ORIGINS must not be '*' in production")

    # Demo users must be disabled in production
    if settings.demo_users_enabled:
        errors.append("DEMO_USERS_ENABLED must be 'false' in production")

    # MFA should be required for admin in production
    if "ADMIN" not in settings.mfa_required_role_list:
        errors.append("MFA should be required for ADMIN role in production")

    if errors:
        raise ValueError(f"Production configuration errors: {', '.join(errors)}")
