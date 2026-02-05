from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api import deps
from app.modules.auth.models import User
from app.modules.clinics.services import PatientService
from app.schemas.clinical import PatientCreate, PatientRead

router = APIRouter()

@router.post("/", response_model=PatientRead)
def create_patient(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    patient_in: PatientCreate
) -> Any:
    """
    Create new patient. Encrypts name.
    """
    service = PatientService(db, current_user.org_id)
    try:
        patient = service.create_patient(
            lab_id=patient_in.lab_id,
            name=patient_in.name,
            age=patient_in.age,
            sex=patient_in.sex,
            phone=patient_in.phone
        )
        # Convert to Read schema (decrypts name via property or manual map?)
        # Service returns ORM object with encrypted_name.
        # We must manually map to Read schema OR add helper in service.
        # Let's rely on the service's get method or helper to decrypt, 
        # BUT for Create response, we know the name we just sent.
        # Ideally, we return what was saved.
        
        # Simpler: Map manually for response
        return PatientRead(
            id=patient.id,
            lab_id=patient.lab_id,
            name=patient_in.name, # Echo back plaintext
            age=patient.age,
            sex=patient.sex,
            created_at=patient.created_at
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[PatientRead])
def read_patients(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve patients. Decrypts names.
    """
    service = PatientService(db, current_user.org_id)
    results = service.list_patients(skip=skip, limit=limit)
    # Service list_patients returns dicts with decrypted names
    return results

@router.get("/{patient_id}", response_model=PatientRead)
def read_patient(
    patient_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    service = PatientService(db, current_user.org_id)
    patient = service.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient
