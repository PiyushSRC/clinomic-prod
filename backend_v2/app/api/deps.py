from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.auth.models import User
from app.core import tenant

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> User:
    """
    Validates token, sets Tenant Context, returns User.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        # 1. Set Context
        org_id_str = payload.get("org_id")
        if not org_id_str:
             raise HTTPException(status_code=403, detail="Could not validate credentials (org)")
        
        tenant.set_tenant_context(tenant.UUID(org_id_str))
        
        # 2. Get User
        token_data = payload # Wrapper?
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
        
    user = db.get(User, payload.get("sub")) # Inaccurate for UUID?
    # BaseRepository usage is preferred but this is global dependency?
    # Actually, we should use repo.
    # For now:
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user
