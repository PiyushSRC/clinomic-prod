from contextvars import ContextVar
from uuid import UUID
from typing import Optional
from fastapi import Request, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
import jwt
from app.core.config import settings

# Context variable to hold the current Org ID
_current_org_id: ContextVar[Optional[UUID]] = ContextVar("current_org_id", default=None)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

def get_current_org_id() -> UUID:
    org_id = _current_org_id.get()
    if not org_id:
        raise HTTPException(status_code=500, detail="Tenant Context Missing")
    return org_id

def set_tenant_context(org_id: UUID):
    _current_org_id.set(org_id)

async def tenant_context_dependency(token: str = Depends(oauth2_scheme)) -> UUID:
    """
    Middleware/Dependency to extract Org ID from JWT and set context.
    Safely handles invalid tokens.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        org_id_str = payload.get("org_id")
        if org_id_str is None:
            raise HTTPException(status_code=401, detail="Invalid Tenant Token")
        
        org_id = UUID(org_id_str)
        set_tenant_context(org_id)
        return org_id
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Could not validate credentials")
