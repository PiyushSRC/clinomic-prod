from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Relationship

# Shared properties
class OrganizationBase(SQLModel):
    name: str = Field(index=True)
    is_active: bool = True

class Organization(OrganizationBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    users: list["User"] = Relationship(back_populates="organization")

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    is_active: bool = True
    full_name: Optional[str] = Field(default=None, nullable=True)
    role: str = "LAB" # LAB, DOCTOR, ADMIN

class User(UserBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hashed_password: str
    org_id: UUID = Field(foreign_key="organization.id", index=True)
    
    organization: Organization = Relationship(back_populates="users")

class AuditLog(SQLModel, table=True):
    """
    Immutable Audit Log.
    Database permissions should REVOKE UPDATE/DELETE on this table.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    org_id: UUID = Field(foreign_key="organization.id", index=True)
    actor_id: str = Field(index=True)
    action: str = Field(index=True)
    entity: str
    entity_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Cryptographic Chain
    prev_hash: str
    signature: str
    
    # Metadata as JSON string (SQLModel doesn't support JSONB directly easily without SaColumn, keep simple for now or use SaColumn if needed later)
    # For core, str is safer for scaffolding compatibility across DBs, but spec asked for JSONB where useful.
    # Audit details usually JSON. 
    details: Optional[str] = None 
