from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.api import deps
from app.modules.auth.models import User
from app.db.repository import BaseRepository
from app.schemas.token import Token

router = APIRouter()

@router.post("/login/access-token", response_model=Token)
def login_access_token(
    db: Session = Depends(deps.get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # 1. Fetch user by email (Cross-tenant lookup requires careful handling or Domain knowledge)
    # Ideally login sends OrgID, but OAuth2 spec Standard is username/password.
    # V2 Design: username usually is "email".
    # Implementation: We search for the user globally OR require "email@org" format?
    # For now: We assume Email Is Global Unique or we find the FIRST match?
    # Better: User must provide OrgID or we lookup?
    # Strict Multi-tenant: Email+OrgID is unique.
    
    # Simple approach for V2 scaffolding: Search by email in all users (System level)
    # BUT wait, pure Tenant Isolation means we shouldn't query across orgs?
    # Exception: Login is the GATEWAY.
    
    # Let's do raw SQL or system-level repo for Login ONLY.
    statement = select(User).where(User.email == form_data.username)
    result = db.execute(statement)
    user = result.scalars().first() # SQLAlchemy style
    # User model has email unique constraint globally or per org?
    # Code says: email: str = Field(unique=True, index=True) -> Global Unique. Safe.

    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    org_id = user.org_id
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, org_id=str(org_id), expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }
