"""MFA (Multi-Factor Authentication) API Router.

This module provides API endpoints for:
- MFA setup and enrollment
- MFA verification
- Backup code management
- Device management
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from core.mfa import MFAManager

router = APIRouter(prefix="/api/mfa", tags=["MFA"])


# Request/Response Models
class MFASetupRequest(BaseModel):
    email: str


class MFASetupResponse(BaseModel):
    provisioning_uri: str
    qr_code_base64: str
    backup_codes: List[str]
    message: str


class MFAVerifyRequest(BaseModel):
    code: str


class MFAVerifyResponse(BaseModel):
    success: bool
    method: Optional[str] = None
    message: str


class MFAStatusResponse(BaseModel):
    is_enabled: bool
    is_setup: bool
    backup_codes_remaining: int
    last_used: Optional[str] = None


class BackupCodesResponse(BaseModel):
    backup_codes: List[str]
    message: str


class DeviceListResponse(BaseModel):
    devices: List[dict]


# Dependency to get MFA manager
def get_mfa_manager(request: Request) -> MFAManager:
    return MFAManager(request.app.state.db)


# Dependency to get current user (from main server)
async def get_current_user_for_mfa(request: Request):
    # This will be injected from the main application
    from server import get_current_user, oauth2_scheme

    token = await oauth2_scheme(request)
    return get_current_user(request, token)


@router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(
    data: MFASetupRequest,
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Initialize MFA setup for the current user.

    Returns QR code and backup codes. User must verify with a code
    from their authenticator app to complete setup.
    """
    user = await get_current_user_for_mfa(request)

    # Check if MFA is already enabled
    status = await mfa_manager.get_mfa_status(user.username, user.org_id)
    if status["isEnabled"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is already enabled for this account")

    result = await mfa_manager.setup_mfa(user_id=user.username, org_id=user.org_id, email=data.email)

    return MFASetupResponse(
        provisioning_uri=result.provisioning_uri,
        qr_code_base64=result.qr_code_base64,
        backup_codes=result.backup_codes,
        message="Scan the QR code with your authenticator app, then verify with a code to complete setup.",
    )


@router.post("/verify-setup", response_model=MFAVerifyResponse)
async def verify_mfa_setup(
    data: MFAVerifyRequest,
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Verify MFA code to complete setup.

    This endpoint completes the MFA enrollment process.
    """
    user = await get_current_user_for_mfa(request)

    success = await mfa_manager.verify_and_enable_mfa(user_id=user.username, org_id=user.org_id, code=data.code)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code. Please try again.")

    return MFAVerifyResponse(success=True, method="totp", message="MFA has been successfully enabled for your account.")


@router.post("/verify", response_model=MFAVerifyResponse)
async def verify_mfa(
    data: MFAVerifyRequest,
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Verify MFA code during login.

    This endpoint is called after password verification when MFA is enabled.
    """
    user = await get_current_user_for_mfa(request)

    success, method = await mfa_manager.verify_mfa(user_id=user.username, org_id=user.org_id, code=data.code)

    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    return MFAVerifyResponse(success=True, method=method, message="MFA verification successful")


@router.get("/status", response_model=MFAStatusResponse)
async def get_mfa_status(
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Get MFA status for the current user."""
    user = await get_current_user_for_mfa(request)

    status = await mfa_manager.get_mfa_status(user.username, user.org_id)

    return MFAStatusResponse(
        is_enabled=status["isEnabled"],
        is_setup=status["isSetup"],
        backup_codes_remaining=status["backupCodesRemaining"],
        last_used=status.get("lastUsed"),
    )


@router.post("/disable", response_model=MFAVerifyResponse)
async def disable_mfa(
    data: MFAVerifyRequest,
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Disable MFA for the current user.

    Requires verification with current MFA code.
    """
    user = await get_current_user_for_mfa(request)

    # Verify current MFA code first
    success, _ = await mfa_manager.verify_mfa(user_id=user.username, org_id=user.org_id, code=data.code)

    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    # Disable MFA
    await mfa_manager.disable_mfa(user.username, user.org_id)

    return MFAVerifyResponse(success=True, message="MFA has been disabled for your account.")


@router.post("/backup-codes/regenerate", response_model=BackupCodesResponse)
async def regenerate_backup_codes(
    data: MFAVerifyRequest,
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Regenerate backup codes.

    This invalidates all existing backup codes.
    Requires verification with current MFA code.
    """
    user = await get_current_user_for_mfa(request)

    # Verify current MFA code first
    success, _ = await mfa_manager.verify_mfa(user_id=user.username, org_id=user.org_id, code=data.code)

    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    # Regenerate backup codes
    codes = await mfa_manager.regenerate_backup_codes(user.username, user.org_id)

    if not codes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled for this account")

    return BackupCodesResponse(backup_codes=codes, message="New backup codes generated. Previous codes are now invalid.")


@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """List registered devices for the current user."""
    user = await get_current_user_for_mfa(request)

    devices = await mfa_manager.devices_collection.find(
        {"userId": user.username, "orgId": user.org_id}, {"_id": 0, "fingerprintHash": 0}
    ).to_list(length=100)

    return DeviceListResponse(devices=devices)


@router.post("/devices/{device_id}/trust")
async def trust_device(
    device_id: str,
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Mark a device as trusted."""
    user = await get_current_user_for_mfa(request)

    # Verify device belongs to user
    device = await mfa_manager.devices_collection.find_one(
        {"deviceId": device_id, "userId": user.username, "orgId": user.org_id}
    )

    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    success = await mfa_manager.trust_device(device_id)

    return {"success": success, "message": "Device marked as trusted"}


@router.delete("/devices/{device_id}")
async def remove_device(
    device_id: str,
    request: Request,
    mfa_manager: MFAManager = Depends(get_mfa_manager),
):
    """Remove a registered device."""
    user = await get_current_user_for_mfa(request)

    result = await mfa_manager.devices_collection.delete_one(
        {"deviceId": device_id, "userId": user.username, "orgId": user.org_id}
    )

    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    return {"success": True, "message": "Device removed"}
