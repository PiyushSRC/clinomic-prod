from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api import deps
from app.modules.auth.models import User
from app.modules.clinics.services import ScreeningService
from app.schemas.clinical import ScreeningCreate, ScreeningRead

router = APIRouter()

@router.post("/", response_model=ScreeningRead)
async def create_screening(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    screening_in: ScreeningCreate
) -> Any:
    """
    Create screening + Run ML.
    """
    service = ScreeningService(db, current_user.org_id)
    
    # Construct complete data payload
    cbc_data = screening_in.extra_data or {}
    cbc_data["hb"] = screening_in.hb
    cbc_data["mcv"] = screening_in.mcv
    
    try:
        screening = await service.create_screening(
            patient_id=screening_in.patient_id,
            cbc_data=cbc_data
        )
        return screening
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        # ML Engine fail
        raise HTTPException(status_code=503, detail=str(e))

@router.get("/patient/{patient_id}", response_model=List[ScreeningRead])
def read_screenings_by_patient(
    patient_id: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    service = ScreeningService(db, current_user.org_id)
    return service.list_by_patient(patient_id)
