from datetime import datetime, timezone
from typing import Optional, Dict
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from app.modules.auth.models import Organization

# Shared properties
class PatientBase(SQLModel):
    lab_id: str = Field(index=True) # Internal Lab Reference ID
    age: int
    sex: str
    phone_hash: Optional[str] = Field(index=True, default=None) # For duplicate checks without PHI

class Patient(PatientBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    org_id: UUID = Field(foreign_key="organization.id", index=True)
    
    # Encrypted PHI (Name, Phone, etc)
    # App logic must encrypt before write
    encrypted_name: str 
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    organization: Organization = Relationship()
    screenings: list["Screening"] = Relationship(back_populates="patient")

class Screening(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    org_id: UUID = Field(foreign_key="organization.id", index=True)
    patient_id: UUID = Field(foreign_key="patient.id", index=True)
    
    # Critical Analytics Columns (Indexed)
    hemoglobin: float = Field(index=True)
    mcv: float = Field(index=True)
    
    # ML Results
    risk_class: int # 1=Normal, 2=Borderline, 3=Deficient
    confidence_score: float
    
    # Validation & Integrity
    model_version: str
    input_hash: str # SHA256 of raw data for duplicate detection
    
    # Full Encrypted Panel Storage
    # Stores the complete LIS payload
    # Defined as JSONB column but content should be encrypted strings or structure
    # For V2 Spec: "raw_panel_encrypted JSONB"
    raw_panel_encrypted: Dict = Field(default={}, sa_column=Column(JSONB))
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    patient: Patient = Relationship(back_populates="screenings")
    organization: Organization = Relationship()
