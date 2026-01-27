"""Multi-Factor Authentication (MFA) Module for Clinomic Platform.

This module provides TOTP-based MFA with:
- MFA setup with QR code generation
- MFA verification
- Backup codes
- Device/session binding
- Anomaly detection hooks
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase


@dataclass
class MFASetupResult:
    """Result of MFA setup."""

    secret: str
    provisioning_uri: str
    qr_code_base64: str
    backup_codes: List[str]


@dataclass
class DeviceFingerprint:
    """Device fingerprint for session binding."""

    user_agent: str
    ip_address: str
    fingerprint_hash: str
    first_seen: str
    last_seen: str
    is_trusted: bool = False


class TOTPGenerator:
    """TOTP (Time-based One-Time Password) implementation."""

    def __init__(self, secret: str, digits: int = 6, interval: int = 30):
        self.secret = secret
        self.digits = digits
        self.interval = interval

    def _get_counter(self, timestamp: Optional[int] = None) -> int:
        """Get the TOTP counter for a timestamp."""
        ts = timestamp or int(time.time())
        return ts // self.interval

    def _hotp(self, counter: int) -> str:
        """Generate HOTP code for a counter."""
        # Decode secret from base32
        secret_bytes = base64.b32decode(self.secret.upper() + "=" * (8 - len(self.secret) % 8))

        # Pack counter as big-endian 64-bit integer
        counter_bytes = struct.pack(">Q", counter)

        # Calculate HMAC-SHA1
        hmac_result = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()

        # Dynamic truncation
        offset = hmac_result[-1] & 0x0F
        code = struct.unpack(">I", hmac_result[offset : offset + 4])[0] & 0x7FFFFFFF

        # Return code with leading zeros
        return str(code % (10**self.digits)).zfill(self.digits)

    def generate(self, timestamp: Optional[int] = None) -> str:
        """Generate current TOTP code."""
        counter = self._get_counter(timestamp)
        return self._hotp(counter)

    def verify(self, code: str, window: int = 1) -> bool:
        """Verify a TOTP code with time window tolerance."""
        current_counter = self._get_counter()

        # Check current and adjacent time windows
        for offset in range(-window, window + 1):
            expected = self._hotp(current_counter + offset)
            if hmac.compare_digest(code, expected):
                return True
        return False


class MFAManager:
    """Manages MFA enrollment, verification, and device binding."""

    ISSUER = "Clinomic Labs"

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.mfa_collection = db["mfa_settings"]
        self.devices_collection = db["user_devices"]
        self.anomaly_collection = db["login_anomalies"]

    @staticmethod
    def generate_secret() -> str:
        """Generate a random TOTP secret."""
        return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

    @staticmethod
    def generate_backup_codes(count: int = 10) -> List[str]:
        """Generate backup codes."""
        return [secrets.token_hex(4).upper() for _ in range(count)]

    def _create_provisioning_uri(self, secret: str, user_email: str, issuer: str = None) -> str:
        """Create TOTP provisioning URI for authenticator apps."""
        issuer = issuer or self.ISSUER
        return f"otpauth://totp/{issuer}:{user_email}?" f"secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"

    def _generate_qr_code(self, uri: str) -> str:
        """Generate QR code as base64 string."""
        try:
            import qrcode
            from qrcode.image.pure import PyPNGImage

            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(uri)
            qr.make(fit=True)

            img = qr.make_image(image_factory=PyPNGImage)
            buffer = io.BytesIO()
            img.save(buffer)
            return base64.b64encode(buffer.getvalue()).decode()
        except ImportError:
            # Return placeholder if qrcode not installed
            return ""

    async def setup_mfa(self, user_id: str, org_id: str, email: str) -> MFASetupResult:
        """Initialize MFA setup for a user."""
        secret = self.generate_secret()
        backup_codes = self.generate_backup_codes()

        # Hash backup codes for storage
        hashed_codes = [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes]

        # Store pending MFA setup (not yet verified)
        await self.mfa_collection.update_one(
            {"userId": user_id, "orgId": org_id},
            {
                "$set": {
                    "userId": user_id,
                    "orgId": org_id,
                    "secret": secret,  # Stored encrypted in production
                    "backupCodes": hashed_codes,
                    "isEnabled": False,  # Not enabled until verified
                    "setupStartedAt": datetime.now(timezone.utc).isoformat(),
                    "verifiedAt": None,
                    "lastUsedAt": None,
                }
            },
            upsert=True,
        )

        uri = self._create_provisioning_uri(secret, email)
        qr_code = self._generate_qr_code(uri)

        return MFASetupResult(secret=secret, provisioning_uri=uri, qr_code_base64=qr_code, backup_codes=backup_codes)

    async def verify_and_enable_mfa(self, user_id: str, org_id: str, code: str) -> bool:
        """Verify MFA code and enable MFA for user."""
        mfa_doc = await self.mfa_collection.find_one({"userId": user_id, "orgId": org_id})

        if not mfa_doc or not mfa_doc.get("secret"):
            return False

        totp = TOTPGenerator(mfa_doc["secret"])
        if not totp.verify(code):
            return False

        # Enable MFA
        await self.mfa_collection.update_one(
            {"userId": user_id, "orgId": org_id},
            {
                "$set": {
                    "isEnabled": True,
                    "verifiedAt": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

        return True

    async def verify_mfa(self, user_id: str, org_id: str, code: str) -> Tuple[bool, str]:
        """Verify MFA code. Returns (success, method used)."""
        mfa_doc = await self.mfa_collection.find_one({"userId": user_id, "orgId": org_id, "isEnabled": True})

        if not mfa_doc:
            return False, "mfa_not_enabled"

        # Try TOTP first
        totp = TOTPGenerator(mfa_doc["secret"])
        if totp.verify(code):
            await self.mfa_collection.update_one(
                {"userId": user_id, "orgId": org_id}, {"$set": {"lastUsedAt": datetime.now(timezone.utc).isoformat()}}
            )
            return True, "totp"

        # Try backup code
        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        if code_hash in mfa_doc.get("backupCodes", []):
            # Remove used backup code
            await self.mfa_collection.update_one(
                {"userId": user_id, "orgId": org_id},
                {"$pull": {"backupCodes": code_hash}, "$set": {"lastUsedAt": datetime.now(timezone.utc).isoformat()}},
            )
            return True, "backup_code"

        return False, "invalid_code"

    async def is_mfa_enabled(self, user_id: str, org_id: str) -> bool:
        """Check if MFA is enabled for a user."""
        mfa_doc = await self.mfa_collection.find_one({"userId": user_id, "orgId": org_id, "isEnabled": True})
        return mfa_doc is not None

    async def disable_mfa(self, user_id: str, org_id: str) -> bool:
        """Disable MFA for a user."""
        result = await self.mfa_collection.update_one(
            {"userId": user_id, "orgId": org_id},
            {
                "$set": {
                    "isEnabled": False,
                    "disabledAt": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        return result.modified_count > 0

    async def regenerate_backup_codes(self, user_id: str, org_id: str) -> Optional[List[str]]:
        """Regenerate backup codes for a user."""
        mfa_doc = await self.mfa_collection.find_one({"userId": user_id, "orgId": org_id, "isEnabled": True})

        if not mfa_doc:
            return None

        backup_codes = self.generate_backup_codes()
        hashed_codes = [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes]

        await self.mfa_collection.update_one({"userId": user_id, "orgId": org_id}, {"$set": {"backupCodes": hashed_codes}})

        return backup_codes

    # Device Fingerprinting & Session Binding

    def _create_device_fingerprint(self, user_agent: str, ip_address: str) -> str:
        """Create a hash-based device fingerprint."""
        data = f"{user_agent}:{ip_address}"
        return hashlib.sha256(data.encode()).hexdigest()

    async def register_device(self, user_id: str, org_id: str, user_agent: str, ip_address: str, trust: bool = False) -> str:
        """Register a device for a user."""
        fingerprint = self._create_device_fingerprint(user_agent, ip_address)
        now = datetime.now(timezone.utc).isoformat()

        device_id = str(uuid.uuid4())

        await self.devices_collection.update_one(
            {"userId": user_id, "orgId": org_id, "fingerprintHash": fingerprint},
            {
                "$set": {
                    "deviceId": device_id,
                    "userId": user_id,
                    "orgId": org_id,
                    "userAgent": user_agent,
                    "ipAddress": ip_address,
                    "fingerprintHash": fingerprint,
                    "lastSeen": now,
                    "isTrusted": trust,
                },
                "$setOnInsert": {
                    "firstSeen": now,
                },
            },
            upsert=True,
        )

        return device_id

    async def is_known_device(self, user_id: str, org_id: str, user_agent: str, ip_address: str) -> Tuple[bool, Optional[str]]:
        """Check if device is known. Returns (is_known, device_id)."""
        fingerprint = self._create_device_fingerprint(user_agent, ip_address)

        device = await self.devices_collection.find_one({"userId": user_id, "orgId": org_id, "fingerprintHash": fingerprint})

        if device:
            return True, device.get("deviceId")
        return False, None

    async def trust_device(self, device_id: str) -> bool:
        """Mark a device as trusted."""
        result = await self.devices_collection.update_one({"deviceId": device_id}, {"$set": {"isTrusted": True}})
        return result.modified_count > 0

    # Anomaly Detection

    async def log_login_attempt(
        self,
        user_id: str,
        org_id: str,
        ip_address: str,
        user_agent: str,
        success: bool,
        mfa_used: bool = False,
        anomaly_flags: Optional[List[str]] = None,
    ) -> None:
        """Log login attempt for anomaly detection."""
        await self.anomaly_collection.insert_one(
            {
                "id": str(uuid.uuid4()),
                "userId": user_id,
                "orgId": org_id,
                "ipAddress": ip_address,
                "userAgent": user_agent,
                "success": success,
                "mfaUsed": mfa_used,
                "anomalyFlags": anomaly_flags or [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def detect_anomalies(self, user_id: str, org_id: str, ip_address: str, user_agent: str) -> List[str]:
        """Detect login anomalies. Returns list of anomaly flags."""
        anomalies = []

        # Check if new device
        is_known, _ = await self.is_known_device(user_id, org_id, user_agent, ip_address)
        if not is_known:
            anomalies.append("new_device")

        # Check for unusual login time (outside 6am-11pm)
        current_hour = datetime.now(timezone.utc).hour
        if current_hour < 6 or current_hour > 23:
            anomalies.append("unusual_time")

        # Check for multiple failed attempts
        recent_failures = await self.anomaly_collection.count_documents(
            {
                "userId": user_id,
                "orgId": org_id,
                "success": False,
                "timestamp": {
                    "$gte": datetime.now(timezone.utc).replace(hour=datetime.now(timezone.utc).hour - 1).isoformat()
                },
            }
        )
        if recent_failures >= 3:
            anomalies.append("multiple_failures")

        return anomalies

    async def get_mfa_status(self, user_id: str, org_id: str) -> Dict[str, Any]:
        """Get MFA status and metadata for a user."""
        mfa_doc = await self.mfa_collection.find_one({"userId": user_id, "orgId": org_id})

        if not mfa_doc:
            return {
                "isEnabled": False,
                "isSetup": False,
                "backupCodesRemaining": 0,
                "lastUsed": None,
            }

        return {
            "isEnabled": mfa_doc.get("isEnabled", False),
            "isSetup": True,
            "backupCodesRemaining": len(mfa_doc.get("backupCodes", [])),
            "lastUsed": mfa_doc.get("lastUsedAt"),
            "verifiedAt": mfa_doc.get("verifiedAt"),
        }
