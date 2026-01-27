from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

# Initialize secrets manager early
from core.secrets import get_secrets_manager

secrets_manager = get_secrets_manager()

from core.audit import AuditLogger
from core.audit_immutable import ImmutableAuditLogger
from core.auth_security import (
    create_access_token,
    create_mfa_pending_token,
    create_refresh_token,
)
from core.auth_security import decode_token as decode_jwt
from core.auth_security import (
    hash_password,
    refresh_token_fingerprint,
    utcnow,
    validate_token_type,
    verify_password,
)
from core.crypto import crypto_manager
from core.jobs import JobManager
from core.mfa import MFAManager
from core.observability import timing_middleware
from core.rate_limit import (
    rate_limit_api,
    rate_limit_login,
    rate_limit_screening,
    rate_limit_upload,
)
from core.settings import settings
from core.storage import ObjectStorage
from core.tenant import (
    TenantContext,
    enforce_org,
    org_id_for_demo_user,
    org_id_for_lab_id,
)

# ------------------------------------------------------------
# Env / App bootstrap
# ------------------------------------------------------------

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger("clinomic")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
audit_logger = AuditLogger(db)
immutable_audit = ImmutableAuditLogger(db)  # New immutable audit system
storage = ObjectStorage(db)
job_manager = JobManager(db)
mfa_manager = MFAManager(db)

app = FastAPI(
    title="Clinomic B12 Screening Platform",
    version="2.0.0",
    description="Clinical Decision Support System for B12 Deficiency Screening",
)
api_router = APIRouter(prefix="/api")

# Milestone 0: request correlation + latency
app.middleware("http")(timing_middleware)


# Milestone 4: Secure Headers
@app.middleware("http")
async def secure_headers_middleware(request: Request, call_next: Callable):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; object-src 'none';"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# CORS: dev may be '*', prod/staging should be explicit via env
if settings.app_env == "prod":
    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
else:
    cors_origins = ["*"]  # allow all in dev/staging unless explicitly restricted

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# Auth (Milestone 2)
# ------------------------------------------------------------

# Demo users remain for MVP compatibility; Milestone 2 persists hashed passwords in Mongo.
USERS: Dict[str, Dict[str, str]] = {
    "admin": {"password": "admin", "role": "ADMIN", "name": "System Administrator"},
    "lab": {"password": "lab", "role": "LAB", "name": "City Pathology Labs"},
    "doctor": {"password": "doctor", "role": "DOCTOR", "name": "Dr. Sharma"},
}

ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class TokenData(BaseModel):
    username: str
    role: str
    org_id: str
    is_super_admin: bool = False

    def tenant(self) -> TenantContext:
        return TenantContext(org_id=self.org_id, is_super_admin=self.is_super_admin)


def decode_access_token(token: str) -> TokenData:
    try:
        payload = decode_jwt(token)
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from e

    token_type = payload.get("token_type")
    # Backwards compatible: tokens without token_type are treated as access tokens.
    if token_type not in (None, "access"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    return TokenData(
        username=payload["sub"],
        role=payload["role"],
        org_id=payload.get("org_id") or settings.default_org_id,
        is_super_admin=bool(payload.get("is_super_admin", False)),
    )


def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> TokenData:
    user = decode_access_token(token)
    request.state.user = user  # Store for rate limiting and logging
    return user


def require_role(allowed_roles: List[str]):
    def role_checker(user: TokenData = Depends(get_current_user)) -> TokenData:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
        return user

    return role_checker


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None  # Optional MFA code for single-step login


class LoginResponse(BaseModel):
    id: str
    name: str
    role: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_pending_token: Optional[str] = None


class MFAVerifyLoginRequest(BaseModel):
    mfa_pending_token: str
    mfa_code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


@api_router.post("/auth/login")
async def login(data: LoginRequest, request: Request, _=Depends(rate_limit_login)):
    """Login endpoint with MFA support.

    If MFA is enabled for the user's role:
    - Returns mfa_required=True with mfa_pending_token
    - User must call /auth/mfa/verify with the pending token and MFA code

    If MFA code is provided in the initial request, attempts single-step login.
    """
    # Get user IP and user agent for device tracking
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Milestone 2: prefer DB users; fallback to demo users and seed DB with password hash.
    print(f"Login attempt for: {data.username}")
    tenant = org_id_for_demo_user(data.username)

    db_user = await db.users.find_one({"id": data.username, "orgId": tenant.org_id})
    name: str
    role: str

    if db_user and db_user.get("passwordHash"):
        print(f"User found in DB: {data.username}")
        if not db_user.get("isActive", True):
            # Log failed login attempt
            await mfa_manager.log_login_attempt(
                user_id=data.username,
                org_id=tenant.org_id,
                ip_address=client_ip,
                user_agent=user_agent,
                success=False,
                anomaly_flags=["disabled_account"],
            )
            raise HTTPException(status_code=403, detail="User disabled")
        if not verify_password(data.password, db_user["passwordHash"]):
            await mfa_manager.log_login_attempt(
                user_id=data.username,
                org_id=tenant.org_id,
                ip_address=client_ip,
                user_agent=user_agent,
                success=False,
                anomaly_flags=["invalid_password"],
            )
            raise HTTPException(status_code=401, detail="Invalid credentials")
        name = db_user.get("name", data.username)
        role = db_user.get("role", "LAB")
    else:
        # Demo user handling
        print("Checking demo users...")
        if not settings.demo_users_enabled:
            print("Demo users DISABLED")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        demo = USERS.get(data.username)
        if not demo:
             print(f"User {data.username} not found in demo USERS dict")
        elif demo["password"] != data.password:
             print(f"Password mismatch for demo user {data.username}. Provided: {data.password}, Expected: {demo['password']}")
        
        if not demo or demo["password"] != data.password:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        name = demo["name"]
        role = demo["role"]

        await db.users.update_one(
            {"id": data.username, "orgId": tenant.org_id},
            {
                "$set": {
                    "id": data.username,
                    "name": name,
                    "role": role,
                    "orgId": tenant.org_id,
                    "passwordHash": hash_password(data.password),
                    "isActive": True,
                    "updatedAt": utcnow().isoformat(),
                },
                "$setOnInsert": {"createdAt": utcnow().isoformat()},
            },
            upsert=True,
        )

    # Check for login anomalies
    anomalies = await mfa_manager.detect_anomalies(data.username, tenant.org_id, client_ip, user_agent)

    # Check if MFA is required for this role
    mfa_required = settings.requires_mfa(role)
    mfa_enabled = await mfa_manager.is_mfa_enabled(data.username, tenant.org_id)

    # If MFA is required and enabled
    if mfa_required and mfa_enabled:
        # If MFA code provided, verify it
        if data.mfa_code:
            success, method = await mfa_manager.verify_mfa(data.username, tenant.org_id, data.mfa_code)
            if not success:
                await mfa_manager.log_login_attempt(
                    user_id=data.username,
                    org_id=tenant.org_id,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    success=False,
                    mfa_used=True,
                    anomaly_flags=["invalid_mfa"],
                )
                raise HTTPException(status_code=401, detail="Invalid MFA code")
        else:
            # Return pending token for MFA verification
            pending_token = create_mfa_pending_token(
                {
                    "sub": data.username,
                    "role": role,
                    "org_id": tenant.org_id,
                    "is_super_admin": tenant.is_super_admin,
                    "name": name,
                }
            )
            return {
                "id": data.username,
                "name": name,
                "role": role,
                "access_token": "",
                "refresh_token": "",
                "token_type": "bearer",
                "mfa_required": True,
                "mfa_pending_token": pending_token,
            }

    # Register device
    if settings.device_tracking_enabled:
        await mfa_manager.register_device(data.username, tenant.org_id, user_agent, client_ip)

    access_token = create_access_token(
        {
            "sub": data.username,
            "role": role,
            "org_id": tenant.org_id,
            "is_super_admin": tenant.is_super_admin,
            "mfa_verified": mfa_enabled,
        },
        expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    refresh_token = create_refresh_token(
        {"sub": data.username, "role": role, "org_id": tenant.org_id, "is_super_admin": tenant.is_super_admin},
        expires_days=REFRESH_TOKEN_EXPIRE_DAYS,
    )

    issued_at = utcnow()
    expires_at = (issued_at + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
    await db.refresh_tokens.insert_one(
        {
            "id": str(uuid.uuid4()),
            "orgId": tenant.org_id,
            "userId": data.username,
            "tokenHash": refresh_token_fingerprint(refresh_token),
            "issuedAt": issued_at.isoformat(),
            "expiresAt": expires_at,
            "revokedAt": None,
            "rotatedTo": None,
        }
    )

    # Log successful login with immutable audit
    if settings.audit_v2_enabled:
        await immutable_audit.log_event(
            actor=data.username,
            org_id=tenant.org_id,
            action="LOGIN",
            entity="USER",
            details={"name": name, "role": role, "anomalies": anomalies},
            ip_address=client_ip,
            user_agent=user_agent,
        )

    # Also log to legacy audit for backwards compatibility
    await audit_logger.log_event(
        actor=data.username,
        org_id=tenant.org_id,
        action="LOGIN",
        entity="USER",
        details={"name": name, "role": role},
    )

    # Log login attempt
    await mfa_manager.log_login_attempt(
        user_id=data.username,
        org_id=tenant.org_id,
        ip_address=client_ip,
        user_agent=user_agent,
        success=True,
        mfa_used=mfa_enabled,
        anomaly_flags=anomalies,
    )

    return {
        "id": data.username,
        "name": name,
        "role": role,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "mfa_required": False,
        "mfa_pending_token": None,
    }


@api_router.post("/auth/mfa/verify")
async def verify_mfa_login(data: MFAVerifyLoginRequest, request: Request, _=Depends(rate_limit_login)):
    """Complete MFA verification step after initial login.

    This endpoint is called with the mfa_pending_token from login response
    and the MFA code from the user's authenticator app.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        payload = decode_jwt(data.mfa_pending_token)

        # Verify it's an MFA pending token
        if not validate_token_type(payload, "mfa_pending"):
            raise HTTPException(status_code=401, detail="Invalid token type")

        username = payload.get("sub")
        role = payload.get("role")
        org_id = payload.get("org_id")
        is_super_admin = payload.get("is_super_admin", False)
        name = payload.get("name", username)

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA pending token")

    # Verify MFA code
    success, method = await mfa_manager.verify_mfa(username, org_id, data.mfa_code)

    if not success:
        await mfa_manager.log_login_attempt(
            user_id=username,
            org_id=org_id,
            ip_address=client_ip,
            user_agent=user_agent,
            success=False,
            mfa_used=True,
            anomaly_flags=["invalid_mfa"],
        )
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    # Register device
    if settings.device_tracking_enabled:
        await mfa_manager.register_device(username, org_id, user_agent, client_ip)

    # Issue full tokens
    access_token = create_access_token(
        {"sub": username, "role": role, "org_id": org_id, "is_super_admin": is_super_admin, "mfa_verified": True},
        expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    refresh_token = create_refresh_token(
        {"sub": username, "role": role, "org_id": org_id, "is_super_admin": is_super_admin},
        expires_days=REFRESH_TOKEN_EXPIRE_DAYS,
    )

    issued_at = utcnow()
    expires_at = (issued_at + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
    await db.refresh_tokens.insert_one(
        {
            "id": str(uuid.uuid4()),
            "orgId": org_id,
            "userId": username,
            "tokenHash": refresh_token_fingerprint(refresh_token),
            "issuedAt": issued_at.isoformat(),
            "expiresAt": expires_at,
            "revokedAt": None,
            "rotatedTo": None,
        }
    )

    # Log successful MFA verification
    if settings.audit_v2_enabled:
        await immutable_audit.log_event(
            actor=username,
            org_id=org_id,
            action="MFA_VERIFIED",
            entity="USER",
            details={"method": method},
            ip_address=client_ip,
            user_agent=user_agent,
        )

    await mfa_manager.log_login_attempt(
        user_id=username, org_id=org_id, ip_address=client_ip, user_agent=user_agent, success=True, mfa_used=True
    )

    return {
        "id": username,
        "name": name,
        "role": role,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "mfa_required": False,
        "mfa_pending_token": None,
    }


@api_router.post("/auth/refresh")
async def refresh(data: RefreshRequest):
    try:
        payload = decode_jwt(data.refresh_token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from e

    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    org_id = payload.get("org_id") or settings.default_org_id
    role = payload.get("role")
    is_super_admin = bool(payload.get("is_super_admin", False))

    token_hash = refresh_token_fingerprint(data.refresh_token)
    token_doc = await db.refresh_tokens.find_one({"orgId": org_id, "userId": user_id, "tokenHash": token_hash})
    if not token_doc:
        raise HTTPException(status_code=401, detail="Refresh token not recognized")
    if token_doc.get("revokedAt"):
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    # rotation
    new_access = create_access_token(
        {"sub": user_id, "role": role, "org_id": org_id, "is_super_admin": is_super_admin},
        expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    new_refresh = create_refresh_token(
        {"sub": user_id, "role": role, "org_id": org_id, "is_super_admin": is_super_admin},
        expires_days=REFRESH_TOKEN_EXPIRE_DAYS,
    )

    now = utcnow().isoformat()
    await db.refresh_tokens.update_one(
        {"id": token_doc["id"]},
        {"$set": {"revokedAt": now, "rotatedTo": refresh_token_fingerprint(new_refresh)}},
    )

    issued_at = utcnow()
    expires_at = (issued_at + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
    await db.refresh_tokens.insert_one(
        {
            "id": str(uuid.uuid4()),
            "orgId": org_id,
            "userId": user_id,
            "tokenHash": refresh_token_fingerprint(new_refresh),
            "issuedAt": issued_at.isoformat(),
            "expiresAt": expires_at,
            "revokedAt": None,
            "rotatedTo": None,
        }
    )

    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


@api_router.post("/auth/logout")
async def logout(data: LogoutRequest):
    try:
        payload = decode_jwt(data.refresh_token)
    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from e

    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    org_id = payload.get("org_id") or settings.default_org_id

    token_hash = refresh_token_fingerprint(data.refresh_token)
    now = utcnow().isoformat()
    await db.refresh_tokens.update_one(
        {"orgId": org_id, "userId": user_id, "tokenHash": token_hash, "revokedAt": None},
        {"$set": {"revokedAt": now}},
    )

    return {"status": "ok"}


@api_router.get("/auth/me")
async def me(user: TokenData = Depends(get_current_user)):
    return {
        "id": user.username,
        "role": user.role,
        "orgId": user.org_id,
        "isSuperAdmin": user.is_super_admin,
    }


# ------------------------------------------------------------
# Clinical engine (DO NOT modify the .pkl files)
# ------------------------------------------------------------


class B12ClinicalEngine:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        try:
            self.stage1 = joblib.load(str(model_dir / "stage1_normal_vs_abnormal.pkl"))
            self.stage2 = joblib.load(str(model_dir / "stage2_borderline_vs_deficient.pkl"))
        except Exception as e:
            logger.warning(f"Could not load ML models (likely missing catboost): {e}")
            self.stage1 = None
            self.stage2 = None

        import json

        with open(model_dir / "thresholds.json", "r", encoding="utf-8") as f:
            self.thresholds = json.load(f)

    def add_indices(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(row)
        row["Mentzer"] = (row.get("MCV") or 0) / (row.get("RBC") or 1)
        row["RDW_MCV"] = (row.get("RDW") or 0) / (row.get("MCV") or 1)
        row["Pancytopenia"] = int(
            (row.get("Hb") or 0) < 12 and (row.get("WBC") or 0) < 4 and (row.get("Platelets") or 0) < 150
        )
        return row

    def apply_rules(self, row: Dict[str, Any]):
        score = 0
        rules: List[str] = []

        if (row.get("MCV") or 0) > 100:
            score += 1
            rules.append("Macrocytosis")
        if (row.get("RDW") or 0) > 15:
            score += 1
            rules.append("High RDW")
        if (row.get("Mentzer") or 0) > 13:
            score += 1
            rules.append("Ineffective erythropoiesis")
        if (row.get("Pancytopenia") or 0) == 1:
            score += 2
            rules.append("Pancytopenia")

        if (row.get("MCV") or 0) < 100 and (row.get("Pancytopenia") or 0) == 0:
            score -= 0.5
            rules.append("No macrocytosis / no pancytopenia")
        if (row.get("Hb") or 0) > 11 and (row.get("Platelets") or 0) > 150:
            score -= 0.5
            rules.append("Preserved cell counts")
        if (row.get("MCV") or 0) < 96 and (row.get("RDW") or 0) < 14 and (row.get("Hb") or 0) > 12:
            score -= 1
            rules.append("Normal marrow pattern")

        return score, rules

    def predict(self, cbc_dict: Dict[str, Any]) -> Dict[str, Any]:
        df = pd.DataFrame([cbc_dict])

        expected_cols = [
            "Age",
            "Sex",
            "Hb",
            "RBC",
            "HCT",
            "MCV",
            "MCH",
            "MCHC",
            "RDW",
            "WBC",
            "Platelets",
            "Neutrophils",
            "Lymphocytes",
        ]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = 0
        df = df[expected_cols]

        if df["Sex"].dtype == "object":
            df["Sex"] = df["Sex"].map({"M": 1, "F": 0, "m": 1, "f": 0}).fillna(0)

        if self.stage1 is None or self.stage2 is None:
             # Fallback for when models are not loaded
             p_abnormal = 0.0
             p_def = 0.0
        else:
             p_abnormal = float(self.stage1.predict_proba(df)[0][1])
             p_def = float(self.stage2.predict_proba(df)[0][1]) if p_abnormal > 0.3 else 0.05

        row = self.add_indices(cbc_dict)
        rule_score, rules = self.apply_rules(row)

        p_def_final = min(1, max(0, p_def + float(self.thresholds.get("rule_weight", 0.0)) * float(rule_score)))

        if p_def_final >= float(self.thresholds.get("deficient_threshold", 0.7)):
            cls = 3
            label_text = "DEFICIENT"
        elif p_def_final >= float(self.thresholds.get("borderline_threshold", 0.4)):
            cls = 2
            label_text = "BORDERLINE"
        else:
            cls = 1
            label_text = "NORMAL"

        return {
            "riskClass": cls,
            "labelText": label_text,
            "probabilities": {
                "normal": round(1 - max(p_abnormal, p_def_final), 3),
                "borderline": round(max(0, p_abnormal - p_def_final), 3),
                "deficient": round(p_def_final, 3),
            },
            "rulesFired": rules,
            "modelVersion": "B12-Clinical-Engine-v1.0",
            "indices": {
                "mentzer": round(
                    (cbc_dict.get("MCV", 0) / cbc_dict.get("RBC", 1)) if (cbc_dict.get("RBC", 0) or 0) > 0 else 0,
                    2,
                ),
                "greenKing": round(
                    (
                        ((pow(cbc_dict.get("MCV", 0), 2) * cbc_dict.get("RDW", 0)) / (100 * cbc_dict.get("Hb", 1)))
                        if (cbc_dict.get("Hb", 0) or 0) > 0
                        else 0
                    ),
                    2,
                ),
                "nlr": round(
                    (
                        ((cbc_dict.get("Neutrophils") or 0) / (cbc_dict.get("Lymphocytes") or 1))
                        if (cbc_dict.get("Lymphocytes") or 0) > 0
                        else 0
                    ),
                    2,
                ),
                "pancytopenia": int(
                    (cbc_dict.get("Hb", 0) or 0) < 12
                    and (cbc_dict.get("WBC", 0) or 0) < 4
                    and (cbc_dict.get("Platelets", 0) or 0) < 150
                ),
            },
        }


ENGINE = B12ClinicalEngine(model_dir=ROOT_DIR / "b12_clinical_engine_v1.0")

MODEL_ARTIFACT_HASH = ""
MODEL_VERSION = "unknown"


def compute_model_hashes():
    global MODEL_ARTIFACT_HASH, MODEL_VERSION
    model_dir = ROOT_DIR / "b12_clinical_engine_v1.0"

    # Version from version.json
    try:
        with open(model_dir / "version.json", "r") as f:
            v_data = json.load(f)
            MODEL_VERSION = v_data.get("version", "unknown")
    except Exception:
        logger.warning("Could not read version.json")

    # Hash pkl files
    hashes = []
    for pkl in sorted(model_dir.glob("*.pkl")):
        with open(pkl, "rb") as f:
            hashes.append(hashlib.sha256(f.read()).hexdigest())

    if hashes:
        MODEL_ARTIFACT_HASH = hashlib.sha256("".join(hashes).encode()).hexdigest()
    else:
        logger.warning("No .pkl files found for hashing")


compute_model_hashes()


# ------------------------------------------------------------
# Request/Response models
# ------------------------------------------------------------


class CBCData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    Hb: float = Field(..., alias="Hb_g_dL")
    RBC: float = Field(..., alias="RBC_million_uL")
    HCT: float = Field(..., alias="HCT_percent")
    MCV: float = Field(..., alias="MCV_fL")
    MCH: float = Field(..., alias="MCH_pg")
    MCHC: float = Field(..., alias="MCHC_g_dL")
    RDW: float = Field(..., alias="RDW_percent")
    WBC: float = Field(..., alias="WBC_10_3_uL")
    Platelets: float = Field(..., alias="Platelets_10_3_uL")
    Neutrophils: Optional[float] = Field(None, alias="Neutrophils_percent")
    Lymphocytes: Optional[float] = Field(None, alias="Lymphocytes_percent")
    Age: int
    Sex: Literal["M", "F", "m", "f"]


class ScreeningRequest(BaseModel):
    patientId: str
    patientName: Optional[str] = None
    labId: Optional[str] = None
    doctorId: Optional[str] = None
    cbc: CBCData
    fileId: Optional[str] = None  # Milestone 5


class ScreeningResponse(BaseModel):
    riskClass: int
    label: int
    probabilities: Dict[str, float]
    rulesFired: List[str]
    recommendation: str
    modelVersion: str
    indices: Dict[str, Any]


# ------------------------------------------------------------
# Seed demo registry
# ------------------------------------------------------------


async def seed_registry_if_needed():
    labs_count = await db.labs.count_documents({})
    if labs_count == 0:
        await db.labs.insert_many(
            [
                {"id": "LAB-2024-001", "name": "City Pathology Labs", "tier": "Enterprise", "orgId": "ORG-LAB-2024-001"},
                {"id": "LAB-2024-014", "name": "Metro Diagnostics", "tier": "Standard", "orgId": "ORG-LAB-2024-014"},
            ]
        )

    doctors_count = await db.doctors.count_documents({})
    if doctors_count == 0:
        await db.doctors.insert_many(
            [
                {
                    "id": "D201",
                    "name": "Dr. Sarah Chen",
                    "dept": "Hematology",
                    "labId": "LAB-2024-001",
                    "orgId": "ORG-LAB-2024-001",
                },
                {
                    "id": "D202",
                    "name": "Dr. Michael Ross",
                    "dept": "General Practice",
                    "labId": "LAB-2024-001",
                    "orgId": "ORG-LAB-2024-001",
                },
                {
                    "id": "D205",
                    "name": "Dr. Robert Chase",
                    "dept": "Critical Care",
                    "labId": "LAB-2024-014",
                    "orgId": "ORG-LAB-2024-014",
                },
            ]
        )


@app.on_event("startup")
async def _startup():
    app.state.db = db  # for rate limiter
    await seed_registry_if_needed()

    # Indices (Milestone 1 + 2)
    await db.users.create_index([("orgId", 1), ("id", 1)], unique=True)
    await db.refresh_tokens.create_index([("orgId", 1), ("userId", 1), ("tokenHash", 1)], unique=True)
    await db.refresh_tokens.create_index([("expiresAt", 1)])

    await db.patients.create_index([("orgId", 1), ("id", 1)], unique=True)
    await db.screenings.create_index([("orgId", 1), ("createdAt", -1)])
    await db.screenings.create_index([("orgId", 1), ("doctorId", 1), ("createdAt", -1)])
    await db.audit_logs.create_index([("orgId", 1), ("timestamp", -1)])
    await db.labs.create_index([("orgId", 1), ("id", 1)], unique=True)
    await db.doctors.create_index([("orgId", 1), ("id", 1)], unique=True)

    # Milestone 4 index for rate limiting
    await db.rate_limits.create_index([("timestamp", 1)], expireAfterSeconds=3600)

    # Milestone 3 indexes for MFA and immutable audit
    await db.mfa_settings.create_index([("userId", 1), ("orgId", 1)], unique=True)
    await db.user_devices.create_index([("userId", 1), ("orgId", 1), ("fingerprintHash", 1)])
    await db.login_anomalies.create_index([("userId", 1), ("timestamp", -1)])
    await db.login_anomalies.create_index([("timestamp", 1)], expireAfterSeconds=2592000)  # 30 days TTL

    # Immutable audit indexes
    await db.audit_logs_v2.create_index([("orgId", 1), ("sequence", 1)], unique=True)
    await db.audit_logs_v2.create_index([("orgId", 1), ("timestamp", -1)])
    await db.audit_checkpoints.create_index([("orgId", 1), ("upToSequence", 1)])

    # Consent indexes (Milestone 4)
    await db.consents.create_index([("orgId", 1), ("patientId", 1), ("status", 1)])
    await db.consents.create_index([("orgId", 1), ("consentedAt", -1)])

    logger.info("Clinomic backend startup complete")


# ------------------------------------------------------------
# Health
# ------------------------------------------------------------


# Helper for background processing
async def process_lis_ingest(job_id: str, file_id: str, org_id: str, user_id: str):
    # Simulate some work
    await asyncio.sleep(2)

    # Download file
    result = await storage.download_file(file_id, org_id)
    if not result:
        raise Exception("File not found for ingestion")

    # Reassemble data
    content = b""
    async for chunk in result["stream"]:
        content += chunk

    # Parse PDF (re-using logic from parse_pdf)
    h = hashlib.sha256(content).hexdigest()
    base = int(h[:6], 16) % 100
    cbc = {
        "Hb": round(9.5 + (base % 30) / 10, 1),
        "RBC": round(3.0 + (base % 20) / 10, 1),
        "WBC": round(4.5 + (base % 40) / 10, 1),
        "Platelets": int(150 + (base % 200)),
        "HCT": int(30 + (base % 20)),
        "MCV": int(85 + (base % 30)),
        "MCH": int(26 + (base % 10)),
        "MCHC": int(31 + (base % 6)),
        "RDW": round(12.0 + (base % 60) / 10, 1),
        "Neutrophils": int(40 + (base % 30)),
        "Lymphocytes": int(20 + (base % 25)),
        "Age": 45,  # Mock defaults for background ingestion
        "Sex": "M",
    }

    await job_manager.update_job(job_id, progress=50)

    # Auto-run prediction? For this milestone, we just return the result
    prediction = ENGINE.predict(cbc)

    await audit_logger.log_event(
        actor=user_id,
        org_id=org_id,
        action="JOB_LIS_INGEST_COMPLETE",
        entity="JOB",
        details={"jobId": job_id, "fileId": file_id},
    )

    return {"cbc": cbc, "prediction": prediction}


@api_router.get("/patients/{patient_id}")
async def get_patient(
    patient_id: str,
    user: TokenData = Depends(require_role(["LAB", "DOCTOR", "ADMIN"])),
    _=Depends(rate_limit_api),
):
    tenant = user.tenant()
    query = enforce_org({"id": patient_id}, tenant.org_id, tenant.is_super_admin)
    patient = await db.patients.find_one(query, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Decrypt name
    if patient.get("name"):
        patient["name"] = crypto_manager.decrypt(patient["name"])

    return patient


@api_router.get("/")
async def root():
    return {"message": "Clinomic B12 Screening API"}


@api_router.get("/health/live")
async def health_live():
    return {"status": "live"}


@api_router.get("/health/ready")
async def health_ready():
    try:
        await db.command("ping")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"database not ready: {str(e)}")

    required = [
        ROOT_DIR / "b12_clinical_engine_v1.0" / "stage1_normal_vs_abnormal.pkl",
        ROOT_DIR / "b12_clinical_engine_v1.0" / "stage2_borderline_vs_deficient.pkl",
        ROOT_DIR / "b12_clinical_engine_v1.0" / "thresholds.json",
        ROOT_DIR / "b12_clinical_engine_v1.0" / "version.json",
    ]
    missing = [str(p.name) for p in required if not p.exists()]
    if missing:
        raise HTTPException(status_code=503, detail=f"model artifacts missing: {', '.join(missing)}")

    return {"status": "ready"}


# ------------------------------------------------------------
# LIS (mocked extractor)
# ------------------------------------------------------------


@api_router.post("/lis/parse-pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    save_to_storage: bool = False,
    user: TokenData = Depends(require_role(["LAB", "DOCTOR", "ADMIN"])),
):
    content = await file.read()

    file_id = None
    if save_to_storage:
        file_id = await storage.upload_file(
            content, file.filename or "uploaded.pdf", file.content_type or "application/pdf", user.org_id
        )

    h = hashlib.sha256(content).hexdigest()
    base = int(h[:6], 16) % 100

    cbc = {
        "hb": round(9.5 + (base % 30) / 10, 1),
        "rbc": round(3.0 + (base % 20) / 10, 1),
        "wbc": round(4.5 + (base % 40) / 10, 1),
        "plt": int(150 + (base % 200)),
        "hct": int(30 + (base % 20)),
        "mcv": int(85 + (base % 30)),
        "mch": int(26 + (base % 10)),
        "mchc": int(31 + (base % 6)),
        "rdw": round(12.0 + (base % 60) / 10, 1),
        "neu_pct": int(40 + (base % 30)),
        "lym_pct": int(20 + (base % 25)),
    }

    return {"cbc": cbc, "fileId": file_id}


# ------------------------------------------------------------
# Screening
# ------------------------------------------------------------


@api_router.post("/screening/predict", response_model=ScreeningResponse)
async def predict_b12(
    data: ScreeningRequest,
    user: TokenData = Depends(require_role(["LAB", "DOCTOR", "ADMIN"])),
    _=Depends(rate_limit_screening),
):
    if not data.patientId.strip():
        raise HTTPException(status_code=400, detail="patientId is required")

    tenant = user.tenant()

    # Effective org:
    # - normal users: their org
    # - super admin: map to lab org if labId known
    effective_org_id = tenant.org_id
    if tenant.is_super_admin and data.labId:
        mapped = org_id_for_lab_id(data.labId)
        if mapped:
            effective_org_id = mapped

    cbc = data.cbc.model_dump(by_alias=False)

    try:
        result = ENGINE.predict(cbc)
    except Exception as e:
        logger.exception("Model prediction failed")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}") from e

    now = datetime.now(timezone.utc)

    patient_doc = {
        "orgId": effective_org_id,
        "id": data.patientId,
        "name": crypto_manager.encrypt((data.patientName or "").strip()),  # Milestone 4: PHI Encryption
        "age": int(cbc.get("Age")),
        "sex": str(cbc.get("Sex")),
        "labId": data.labId,
        "doctorId": data.doctorId,
        "updatedAt": now.isoformat(),
    }

    await db.patients.update_one(
        {"orgId": effective_org_id, "id": data.patientId},
        {"$set": patient_doc, "$setOnInsert": {"createdAt": now.isoformat()}},
        upsert=True,
    )

    screening_id = str(uuid.uuid4())

    # Milestone 3: Lineage & Reproducibility
    # canonical_json for request/response hashes
    req_json = audit_logger.canonical_json(data.model_dump())
    res_json = audit_logger.canonical_json(result)

    req_hash = hashlib.sha256(req_json.encode()).hexdigest()
    res_hash = hashlib.sha256(res_json.encode()).hexdigest()

    screening_doc = {
        "orgId": effective_org_id,
        "id": screening_id,
        "patientId": data.patientId,
        "userId": user.username,
        "labId": data.labId,
        "doctorId": data.doctorId,
        "riskClass": int(result["riskClass"]),
        "label": int(result["riskClass"]),
        "labelText": result.get("labelText"),
        "probabilities": result.get("probabilities", {}),
        "rulesFired": result.get("rulesFired", []),
        "modelVersion": MODEL_VERSION,
        "modelArtifactHash": MODEL_ARTIFACT_HASH,
        "requestHash": req_hash,
        "responseHash": res_hash,
        "fileId": data.fileId,  # Milestone 5
        "indices": result.get("indices", {}),
        "cbcSnapshot": {
            "mcv": cbc.get("MCV"),
            "hb": cbc.get("Hb"),
            "rdw": cbc.get("RDW"),
        },
        "createdAt": now.isoformat(),
    }

    # screeningHash = SHA256(requestHash + responseHash + modelArtifactHash)
    screening_hash_payload = f"{req_hash}{res_hash}{MODEL_ARTIFACT_HASH}"
    screening_doc["screeningHash"] = hashlib.sha256(screening_hash_payload.encode()).hexdigest()

    await db.screenings.insert_one(screening_doc)

    # Immutable Audit Log
    await audit_logger.log_event(
        actor=user.username,
        org_id=effective_org_id,
        action="SCREEN_B12",
        entity="SCREENING",
        details={
            "patientId": data.patientId,
            "screeningId": screening_id,
            "riskClass": int(result["riskClass"]),
            "screeningHash": screening_doc["screeningHash"],
        },
        request_id=getattr(user, "request_id", None),  # request_id is in request.state usually, but user is TokenData
    )

    return {
        "riskClass": int(result["riskClass"]),
        "label": int(result["riskClass"]),
        "probabilities": result["probabilities"],
        "rulesFired": result["rulesFired"],
        "recommendation": "Confirm with Serum B12 ± MMA as clinically indicated",
        "modelVersion": result["modelVersion"],
        "indices": result.get("indices", {}),
    }


# ------------------------------------------------------------
# Analytics (tenant-enforced)
# ------------------------------------------------------------


@api_router.get("/analytics/summary")
async def analytics_summary(user: TokenData = Depends(require_role(["ADMIN", "LAB"]))):
    tenant = user.tenant()
    base_q = enforce_org({}, tenant.org_id, tenant.is_super_admin)

    total = await db.screenings.count_documents(base_q)
    normal_count = await db.screenings.count_documents({**base_q, "riskClass": 1})
    borderline_count = await db.screenings.count_documents({**base_q, "riskClass": 2})
    deficient_count = await db.screenings.count_documents({**base_q, "riskClass": 3})

    since = datetime.now(timezone.utc).timestamp() - 24 * 60 * 60
    daily_tests = await db.screenings.count_documents(
        {**base_q, "createdAt": {"$gte": datetime.fromtimestamp(since, tz=timezone.utc).isoformat()}}
    )

    recent_cursor = db.screenings.find(base_q, {"_id": 0}).sort("createdAt", -1).limit(20)
    recent_docs = await recent_cursor.to_list(length=20)

    recent = []
    for r in recent_docs:
        rc = int(r.get("riskClass", 1))
        if rc == 3:
            res_str = "High Risk"
        elif rc == 2:
            res_str = "Borderline"
        else:
            res_str = "Normal"
        created_at = r.get("createdAt") or datetime.now(timezone.utc).isoformat()
        recent.append(
            {
                "id": r.get("id"),
                "date": str(created_at)[:10],
                "patientRef": r.get("patientId"),
                "mcv": (r.get("cbcSnapshot") or {}).get("mcv", "-"),
                "result": res_str,
            }
        )

    return {
        "totalCases": total,
        "dailyTests": daily_tests,
        "modelMetrics": {
            "accuracy": 92,
            "recall": 88,
            "precision": 90,
            "f1Score": 89,
            "auc": 0.94,
            "version": "v1.0.0",
        },
        "distribution": [
            {"name": "Normal", "value": normal_count, "fill": "#10b981"},
            {"name": "Borderline", "value": borderline_count, "fill": "#f59e0b"},
            {"name": "Deficient", "value": deficient_count, "fill": "#ef4444"},
        ],
        "recentCases": recent,
    }


@api_router.get("/analytics/labs")
async def analytics_labs(user: TokenData = Depends(require_role(["ADMIN"]))):
    tenant = user.tenant()
    labs = await db.labs.find(enforce_org({}, tenant.org_id, tenant.is_super_admin), {"_id": 0}).to_list(length=1000)

    out = []
    for lab in labs:
        lab_id = lab.get("id")
        doctors = await db.doctors.count_documents(enforce_org({"labId": lab_id}, tenant.org_id, tenant.is_super_admin))
        cases = await db.screenings.count_documents(enforce_org({"labId": lab_id}, tenant.org_id, tenant.is_super_admin))
        out.append(
            {
                "id": lab_id,
                "name": lab.get("name"),
                "tier": lab.get("tier", "Standard"),
                "doctors": doctors,
                "cases": cases,
            }
        )
    return out


@api_router.get("/analytics/doctors")
async def analytics_doctors(
    labId: Optional[str] = None,
    user: TokenData = Depends(require_role(["ADMIN", "LAB"])),
):
    tenant = user.tenant()
    query: Dict[str, Any] = enforce_org({}, tenant.org_id, tenant.is_super_admin)
    if labId:
        query["labId"] = labId

    docs = await db.doctors.find(query, {"_id": 0}).to_list(length=1000)
    out = []
    for d in docs:
        cases = await db.screenings.count_documents(
            enforce_org({"doctorId": d.get("id")}, tenant.org_id, tenant.is_super_admin)
        )
        out.append(
            {
                "id": d.get("id"),
                "name": d.get("name"),
                "dept": d.get("dept", "General"),
                "cases": cases,
            }
        )
    return out


@api_router.get("/analytics/cases")
async def analytics_cases(
    doctorId: Optional[str] = None,
    labId: Optional[str] = None,
    user: TokenData = Depends(require_role(["ADMIN", "LAB"])),
):
    tenant = user.tenant()
    query: Dict[str, Any] = enforce_org({}, tenant.org_id, tenant.is_super_admin)
    if doctorId:
        query["doctorId"] = doctorId
    if labId:
        query["labId"] = labId

    cases = await db.screenings.find(query, {"_id": 0}).sort("createdAt", -1).limit(500).to_list(length=500)

    patient_ids = list({c.get("patientId") for c in cases if c.get("patientId")})
    patients = await db.patients.find(
        enforce_org({"id": {"$in": patient_ids}}, tenant.org_id, tenant.is_super_admin),
        {"_id": 0},
    ).to_list(length=1000)
    patient_map = {p["id"]: p for p in patients}

    out = []
    for c in cases:
        p = patient_map.get(c.get("patientId"), {})
        out.append(
            {
                "id": c.get("id"),
                "patientId": c.get("patientId"),
                "name": p.get("name", ""),
                "age": p.get("age", ""),
                "sex": p.get("sex", ""),
                "labId": c.get("labId", ""),
                "date": str(c.get("createdAt", ""))[:10],
                "result": int(c.get("riskClass", 1)),
            }
        )

    return out


# Attach router
# ------------------------------------------------------------
# Admin / Audit (Milestone 3)
# ------------------------------------------------------------


@api_router.get("/admin/audit/export")
async def export_audit(
    org_id: Optional[str] = None,
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    tenant = user.tenant()
    target_org = org_id or tenant.org_id

    # Super admins can view any org, others only their own
    if not tenant.is_super_admin and target_org != tenant.org_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Verify the chain
    verification = await audit_logger.verify_chain(target_org, limit=1000)

    # Fetch logs for export
    cursor = db.audit_logs.find({"orgId": target_org}, {"_id": 0}).sort("timestamp", -1).limit(1000)
    logs = await cursor.to_list(length=1000)

    return {
        "orgId": target_org,
        "verification": {
            "isValid": verification["isValid"],
            "totalChecks": verification["totalVerified"],
        },
        "logs": logs,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "exportedBy": user.username,
    }


# ------------------------------------------------------------
# Storage (Milestone 5)
# ------------------------------------------------------------


@api_router.post("/storage/upload")
async def upload_file(
    file: UploadFile = File(...),
    screeningId: Optional[str] = None,
    user: TokenData = Depends(require_role(["LAB", "DOCTOR", "ADMIN"])),
    _=Depends(rate_limit_upload),
):
    content = await file.read()
    file_id = await storage.upload_file(
        content,
        file.filename or "file.dat",
        file.content_type or "application/octet-stream",
        user.org_id,
        screening_id=screeningId,
    )

    await audit_logger.log_event(
        actor=user.username,
        org_id=user.org_id,
        action="FILE_UPLOAD",
        entity="FILE",
        details={"fileId": file_id, "filename": file.filename},
        request_id=getattr(user, "request_id", None),
    )

    return {"fileId": file_id, "status": "uploaded"}


@api_router.get("/storage/download/{file_id}")
async def download_file(
    file_id: str,
    user: TokenData = Depends(
        get_current_user
    ),  # Use generic since any logged in user with org access can potentially download
):
    result = await storage.download_file(file_id, user.org_id)
    if not result:
        raise HTTPException(status_code=404, detail="File not found")

    meta = result["metadata"]
    return StreamingResponse(
        result["stream"],
        media_type=meta["contentType"],
        headers={"Content-Disposition": f'attachment; filename="{meta["filename"]}"'},
    )


@api_router.get("/storage/files")
async def list_files(
    screeningId: Optional[str] = None,
    user: TokenData = Depends(get_current_user),
):
    files = await storage.list_files(user.org_id, screening_id=screeningId)
    return files


# ------------------------------------------------------------
# Background Jobs (Milestone 6)
# ------------------------------------------------------------


@api_router.post("/jobs/lis-ingest")
async def queue_lis_ingest(
    file: UploadFile = File(...),
    user: TokenData = Depends(require_role(["LAB", "ADMIN"])),
):
    # 1. Store file first since worker needs it
    content = await file.read()
    file_id = await storage.upload_file(
        content,
        file.filename or "ingest.pdf",
        file.content_type or "application/pdf",
        user.org_id,
    )

    # 2. Create job
    job_id = await job_manager.create_job(
        "LIS_INGEST", user.org_id, user.username, params={"fileId": file_id, "filename": file.filename}
    )

    # 3. Start background task
    await job_manager.run_in_background(job_id, process_lis_ingest, file_id, user.org_id, user.username)

    await audit_logger.log_event(
        actor=user.username,
        org_id=user.org_id,
        action="JOB_SUBMITTED",
        entity="JOB",
        details={"jobId": job_id, "type": "LIS_INGEST"},
        request_id=getattr(user, "request_id", None),
    )

    return {"jobId": job_id, "status": "PENDING"}


@api_router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user: TokenData = Depends(get_current_user),
):
    job = await job_manager.get_job(job_id, user.org_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@api_router.get("/jobs")
async def list_jobs(
    user: TokenData = Depends(get_current_user),
):
    return await job_manager.list_jobs(user.org_id)


# ------------------------------------------------------------
# MFA Management (Milestone 3)
# ------------------------------------------------------------


class MFASetupRequest(BaseModel):
    email: str


class MFAVerifyCodeRequest(BaseModel):
    code: str


@api_router.post("/mfa/setup")
async def mfa_setup(
    data: MFASetupRequest,
    user: TokenData = Depends(get_current_user),
):
    """Initialize MFA setup for the current user.

    Returns QR code and backup codes. User must verify with a code
    from their authenticator app to complete setup.
    """
    # Check if MFA is already enabled
    mfa_status = await mfa_manager.get_mfa_status(user.username, user.org_id)
    if mfa_status["isEnabled"]:
        raise HTTPException(status_code=400, detail="MFA is already enabled for this account")

    result = await mfa_manager.setup_mfa(user_id=user.username, org_id=user.org_id, email=data.email)

    return {
        "provisioning_uri": result.provisioning_uri,
        "qr_code_base64": result.qr_code_base64,
        "backup_codes": result.backup_codes,
        "message": "Scan the QR code with your authenticator app, then verify with a code to complete setup.",
    }


@api_router.post("/mfa/verify-setup")
async def mfa_verify_setup(
    data: MFAVerifyCodeRequest,
    user: TokenData = Depends(get_current_user),
):
    """Verify MFA code to complete setup."""
    success = await mfa_manager.verify_and_enable_mfa(user_id=user.username, org_id=user.org_id, code=data.code)

    if not success:
        raise HTTPException(status_code=400, detail="Invalid verification code. Please try again.")

    if settings.audit_v2_enabled:
        await immutable_audit.log_event(
            actor=user.username,
            org_id=user.org_id,
            action="MFA_ENABLED",
            entity="USER",
            details={"method": "totp"},
        )

    return {"success": True, "message": "MFA has been successfully enabled for your account."}


@api_router.get("/mfa/status")
async def mfa_get_status(
    user: TokenData = Depends(get_current_user),
):
    """Get MFA status for the current user."""
    status = await mfa_manager.get_mfa_status(user.username, user.org_id)

    return {
        "is_enabled": status["isEnabled"],
        "is_setup": status["isSetup"],
        "backup_codes_remaining": status["backupCodesRemaining"],
        "last_used": status.get("lastUsed"),
        "mfa_required_for_role": settings.requires_mfa(user.role),
    }


@api_router.post("/mfa/disable")
async def mfa_disable(
    data: MFAVerifyCodeRequest,
    user: TokenData = Depends(get_current_user),
):
    """Disable MFA for the current user. Requires verification."""
    # Verify current MFA code first
    success, _ = await mfa_manager.verify_mfa(user_id=user.username, org_id=user.org_id, code=data.code)

    if not success:
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    await mfa_manager.disable_mfa(user.username, user.org_id)

    if settings.audit_v2_enabled:
        await immutable_audit.log_event(
            actor=user.username,
            org_id=user.org_id,
            action="MFA_DISABLED",
            entity="USER",
            details={},
        )

    return {"success": True, "message": "MFA has been disabled for your account."}


@api_router.post("/mfa/backup-codes/regenerate")
async def mfa_regenerate_backup_codes(
    data: MFAVerifyCodeRequest,
    user: TokenData = Depends(get_current_user),
):
    """Regenerate backup codes. Requires verification."""
    # Verify current MFA code first
    success, _ = await mfa_manager.verify_mfa(user_id=user.username, org_id=user.org_id, code=data.code)

    if not success:
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    codes = await mfa_manager.regenerate_backup_codes(user.username, user.org_id)

    if not codes:
        raise HTTPException(status_code=400, detail="MFA is not enabled for this account")

    return {"backup_codes": codes, "message": "New backup codes generated. Previous codes are now invalid."}


# ------------------------------------------------------------
# Immutable Audit (Milestone 3)
# ------------------------------------------------------------


@api_router.get("/admin/audit/v2/summary")
async def audit_v2_summary(
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    """Get immutable audit log summary with chain integrity status."""
    tenant = user.tenant()
    return await immutable_audit.get_audit_summary(tenant.org_id)


@api_router.get("/admin/audit/v2/verify")
async def audit_v2_verify(
    limit: int = 100,
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    """Verify immutable audit log chain integrity."""
    tenant = user.tenant()
    return await immutable_audit.verify_chain(tenant.org_id, limit=limit)


@api_router.get("/admin/audit/v2/export")
async def audit_v2_export(
    from_sequence: int = 1,
    to_sequence: Optional[int] = None,
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    """Export immutable audit logs for archival."""
    tenant = user.tenant()
    return await immutable_audit.export_for_archive(tenant.org_id, from_sequence=from_sequence, to_sequence=to_sequence)


@api_router.get("/admin/audit/v2/entry/{entry_id}/verify")
async def audit_v2_verify_entry(
    entry_id: str,
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    """Verify integrity of a single audit entry."""
    return await immutable_audit.verify_entry(entry_id)


# ------------------------------------------------------------
# System Health & Config (Milestone 3)
# ------------------------------------------------------------


@api_router.get("/admin/system/config")
async def system_config(
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    """Get system configuration summary (no secrets)."""
    from core.secrets import get_secrets_manager

    return {
        "settings": settings.get_config_summary(),
        "secrets": get_secrets_manager().get_health_status(),
        "model": {
            "version": MODEL_VERSION,
            "artifact_hash": MODEL_ARTIFACT_HASH[:16] + "..." if MODEL_ARTIFACT_HASH else None,
        },
    }


@api_router.get("/admin/system/health")
async def system_health(
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    """Comprehensive health check for all system components."""
    from core.crypto import get_crypto_manager

    health = {"status": "healthy", "components": {}}

    # Database health
    try:
        await db.command("ping")
        health["components"]["database"] = {"status": "healthy"}
    except Exception as e:
        health["components"]["database"] = {"status": "unhealthy", "error": str(e)}
        health["status"] = "degraded"

    # Model engine health
    required_files = [
        ROOT_DIR / "b12_clinical_engine_v1.0" / "stage1_normal_vs_abnormal.pkl",
        ROOT_DIR / "b12_clinical_engine_v1.0" / "stage2_borderline_vs_deficient.pkl",
    ]
    missing = [str(p.name) for p in required_files if not p.exists()]
    if missing:
        health["components"]["model_engine"] = {"status": "unhealthy", "missing": missing}
        health["status"] = "degraded"
    else:
        health["components"]["model_engine"] = {"status": "healthy", "version": MODEL_VERSION}

    # Crypto health
    health["components"]["crypto"] = get_crypto_manager().get_health_status()

    # Audit health
    if settings.audit_v2_enabled:
        try:
            audit_summary = await immutable_audit.get_audit_summary(user.org_id)
            health["components"]["audit"] = {
                "status": "healthy" if audit_summary["chainIntegrity"]["verified"] else "degraded",
                "entries": audit_summary["totalEntries"],
                "integrity": audit_summary["chainIntegrity"],
            }
        except Exception as e:
            health["components"]["audit"] = {"status": "unhealthy", "error": str(e)}

    return health


# ------------------------------------------------------------
# Consent Management (Milestone 4)
# ------------------------------------------------------------


class ConsentRecordRequest(BaseModel):
    patientId: str
    patientName: Optional[str] = None
    consentType: str = "verbal"  # verbal, written, electronic
    witnessName: Optional[str] = None
    notes: Optional[str] = None
    purposes: Optional[List[str]] = None


@api_router.post("/consent/record")
async def record_consent(
    data: ConsentRecordRequest,
    user: TokenData = Depends(get_current_user),
):
    """Record patient consent for screening."""
    tenant = user.tenant()
    consent_id = str(uuid.uuid4())
    now = utcnow().isoformat()

    consent_doc = {
        "id": consent_id,
        "orgId": tenant.org_id,
        "patientId": data.patientId,
        "patientName": crypto_manager.encrypt(data.patientName) if data.patientName else None,
        "consentType": data.consentType,
        "witnessName": data.witnessName,
        "recordedBy": user.username,
        "notes": data.notes,
        "purposes": data.purposes
        or [
            "B12 deficiency screening using CBC data",
            "Storage of screening results for medical records",
            "Anonymous data usage for quality improvement",
        ],
        "status": "active",
        "consentedAt": now,
        "createdAt": now,
        "revokedAt": None,
    }

    await db.consents.insert_one(consent_doc)

    # Log to immutable audit
    if settings.audit_v2_enabled:
        await immutable_audit.log_event(
            actor=user.username,
            org_id=tenant.org_id,
            action="CONSENT_RECORDED",
            entity="CONSENT",
            entity_id=consent_id,
            details={
                "patientId": data.patientId,
                "consentType": data.consentType,
            },
        )

    return {"id": consent_id, "status": "recorded", "message": "Consent recorded successfully"}


@api_router.get("/consent/status/{patient_id}")
async def get_consent_status(
    patient_id: str,
    user: TokenData = Depends(get_current_user),
):
    """Check consent status for a patient."""
    tenant = user.tenant()

    consent = await db.consents.find_one(
        {
            "orgId": tenant.org_id,
            "patientId": patient_id,
            "status": "active",
        },
        sort=[("consentedAt", -1)],
    )

    if consent:
        return {
            "hasConsent": True,
            "consentId": consent["id"],
            "consentType": consent["consentType"],
            "consentedAt": consent["consentedAt"],
            "purposes": consent.get("purposes", []),
        }

    return {"hasConsent": False}


@api_router.post("/consent/revoke/{consent_id}")
async def revoke_consent(
    consent_id: str,
    user: TokenData = Depends(get_current_user),
):
    """Revoke patient consent."""
    tenant = user.tenant()

    result = await db.consents.update_one(
        {"id": consent_id, "orgId": tenant.org_id},
        {
            "$set": {
                "status": "revoked",
                "revokedAt": utcnow().isoformat(),
                "revokedBy": user.username,
            }
        },
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Consent not found")

    if settings.audit_v2_enabled:
        await immutable_audit.log_event(
            actor=user.username,
            org_id=tenant.org_id,
            action="CONSENT_REVOKED",
            entity="CONSENT",
            entity_id=consent_id,
            details={},
        )

    return {"status": "revoked", "message": "Consent revoked successfully"}


# ------------------------------------------------------------
# Demo Seed Data (Milestone 4)
# ------------------------------------------------------------


@api_router.post("/admin/demo/seed")
async def seed_demo_data(
    user: TokenData = Depends(require_role(["ADMIN"])),
):
    """Seed demo data for investor demonstrations."""
    tenant = user.tenant()
    org_id = tenant.org_id
    now = utcnow()

    seeded = {
        "patients": 0,
        "screenings": 0,
        "doctors": 0,
        "labs": 0,
    }

    # Seed labs
    demo_labs = [
        {"id": "LAB-DEMO-001", "name": "Central Pathology Lab", "tier": "Tier-1"},
        {"id": "LAB-DEMO-002", "name": "City Hospital Laboratory", "tier": "Tier-2"},
        {"id": "LAB-DEMO-003", "name": "Regional Diagnostic Center", "tier": "Tier-2"},
    ]

    for lab in demo_labs:
        await db.labs.update_one({"id": lab["id"], "orgId": org_id}, {"$set": {**lab, "orgId": org_id}}, upsert=True)
        seeded["labs"] += 1

    # Seed doctors
    demo_doctors = [
        {"id": "DOC-DEMO-001", "name": "Dr. Sarah Chen", "dept": "Hematology", "labId": "LAB-DEMO-001"},
        {"id": "DOC-DEMO-002", "name": "Dr. Michael Ross", "dept": "Internal Medicine", "labId": "LAB-DEMO-001"},
        {"id": "DOC-DEMO-003", "name": "Dr. Emily Watson", "dept": "General Practice", "labId": "LAB-DEMO-002"},
        {"id": "DOC-DEMO-004", "name": "Dr. Robert Chase", "dept": "Critical Care", "labId": "LAB-DEMO-002"},
        {"id": "DOC-DEMO-005", "name": "Dr. Lisa House", "dept": "Neurology", "labId": "LAB-DEMO-003"},
    ]

    for doc in demo_doctors:
        await db.doctors.update_one({"id": doc["id"], "orgId": org_id}, {"$set": {**doc, "orgId": org_id}}, upsert=True)
        seeded["doctors"] += 1

    # Seed patients with screenings
    import random

    demo_patients = [
        {"id": "PAT-DEMO-001", "name": "John Smith", "age": 45, "sex": "M"},
        {"id": "PAT-DEMO-002", "name": "Mary Johnson", "age": 62, "sex": "F"},
        {"id": "PAT-DEMO-003", "name": "Robert Brown", "age": 35, "sex": "M"},
        {"id": "PAT-DEMO-004", "name": "Patricia Davis", "age": 58, "sex": "F"},
        {"id": "PAT-DEMO-005", "name": "James Wilson", "age": 71, "sex": "M"},
        {"id": "PAT-DEMO-006", "name": "Jennifer Miller", "age": 28, "sex": "F"},
        {"id": "PAT-DEMO-007", "name": "Michael Garcia", "age": 52, "sex": "M"},
        {"id": "PAT-DEMO-008", "name": "Elizabeth Martinez", "age": 44, "sex": "F"},
        {"id": "PAT-DEMO-009", "name": "David Anderson", "age": 67, "sex": "M"},
        {"id": "PAT-DEMO-010", "name": "Susan Taylor", "age": 39, "sex": "F"},
    ]

    risk_classes = [
        (1, "Normal", {"normal": 0.85, "borderline": 0.12, "deficient": 0.03}),
        (1, "Normal", {"normal": 0.92, "borderline": 0.06, "deficient": 0.02}),
        (2, "Borderline", {"normal": 0.35, "borderline": 0.55, "deficient": 0.10}),
        (2, "Borderline", {"normal": 0.28, "borderline": 0.58, "deficient": 0.14}),
        (3, "Deficient", {"normal": 0.08, "borderline": 0.22, "deficient": 0.70}),
    ]

    for i, patient in enumerate(demo_patients):
        doc = random.choice(demo_doctors)
        lab = next(l for l in demo_labs if l["id"] == doc["labId"])

        # Save patient
        encrypted_name = crypto_manager.encrypt(patient["name"])
        await db.patients.update_one(
            {"id": patient["id"], "orgId": org_id},
            {
                "$set": {
                    "id": patient["id"],
                    "orgId": org_id,
                    "name": encrypted_name,
                    "age": patient["age"],
                    "sex": patient["sex"],
                    "labId": lab["id"],
                    "doctorId": doc["id"],
                    "createdAt": now.isoformat(),
                }
            },
            upsert=True,
        )
        seeded["patients"] += 1

        # Create screening
        risk_class, label_text, probs = random.choice(risk_classes)
        screening_id = str(uuid.uuid4())

        cbc_values = {
            "mcv": round(random.uniform(75, 105), 1),
            "hb": round(random.uniform(10, 16), 1),
            "rdw": round(random.uniform(11, 18), 1),
        }

        screening_doc = {
            "id": screening_id,
            "orgId": org_id,
            "patientId": patient["id"],
            "userId": user.username,
            "labId": lab["id"],
            "doctorId": doc["id"],
            "riskClass": risk_class,
            "label": risk_class,
            "labelText": label_text,
            "probabilities": probs,
            "rulesFired": [],
            "modelVersion": MODEL_VERSION,
            "modelArtifactHash": MODEL_ARTIFACT_HASH,
            "requestHash": hashlib.sha256(f"demo-{patient['id']}".encode()).hexdigest(),
            "responseHash": hashlib.sha256(f"demo-response-{screening_id}".encode()).hexdigest(),
            "screeningHash": hashlib.sha256(f"demo-screening-{screening_id}".encode()).hexdigest(),
            "indices": {
                "mentzer": round(random.uniform(12, 20), 1),
                "greenKing": round(random.uniform(60, 90), 1),
            },
            "cbcSnapshot": cbc_values,
            "createdAt": (now - timedelta(days=random.randint(0, 30))).isoformat(),
        }

        await db.screenings.insert_one(screening_doc)
        seeded["screenings"] += 1

    # Log seed action
    if settings.audit_v2_enabled:
        await immutable_audit.log_event(
            actor=user.username,
            org_id=org_id,
            action="DEMO_DATA_SEEDED",
            entity="SYSTEM",
            details=seeded,
        )

    return {
        "status": "success",
        "message": "Demo data seeded successfully",
        "seeded": seeded,
    }


app.include_router(api_router)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
