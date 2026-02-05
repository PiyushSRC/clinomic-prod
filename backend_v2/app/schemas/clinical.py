from pydantic import BaseModel
from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime

# Patient Schemas
class PatientCreate(BaseModel):
    lab_id: str
    name: str # Plaintext input, will be encrypted by service
    age: int
    sex: str
    phone: Optional[str] = None

class PatientRead(BaseModel):
    id: UUID
    lab_id: str
    name: str # Decrypted
    age: int
    sex: str
    created_at: datetime

# Screening Schemas
class ScreeningCreate(BaseModel):
    patient_id: UUID
    hb: float
    mcv: float
    # Other CBC fields passed in generic dict or explicit here?
    # For V2 Pilot, explicit criticals + extra dict
    extra_data: Optional[Dict] = {}

class ScreeningRead(BaseModel):
    id: UUID
    patient_id: UUID
    hemoglobin: float
    mcv: float
    risk_class: int
    confidence_score: float
    created_at: datetime
