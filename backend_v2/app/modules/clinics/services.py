from uuid import UUID
from typing import List, Optional
from sqlmodel import Session, select
from app.core import crypto
from app.modules.clinics.models import Patient, Screening
from app.db.repository import BaseRepository
from app.ml.engine import engine

class PatientService:
    def __init__(self, db: Session, org_id: UUID):
        self.repo = BaseRepository(Patient, db, org_id)
        self.org_id = org_id

    def create_patient(self, lab_id: str, name: str, age: int, sex: str, phone: Optional[str] = None) -> Patient:
        # 1. Encrypt Data
        encrypted_name = crypto.crypto.encrypt(name)
        phone_hash = None # Hash phone for lookup if needed
        
        # 2. Create Object
        patient = Patient(
            lab_id=lab_id,
            age=age,
            sex=sex,
            phone_hash=phone_hash,
            encrypted_name=encrypted_name,
            org_id=self.org_id
        )
        return self.repo.create(patient)

    def get_patient(self, patient_id: UUID) -> Optional[dict]:
        # Return dict with decrypted name
        patient = self.repo.get(patient_id)
        if not patient:
            return None
        
        # Decrypt on read
        try:
            name = crypto.crypto.decrypt(patient.encrypted_name)
        except Exception:
            name = "DECRYPTION_ERROR"
            
        return {
            "id": patient.id,
            "lab_id": patient.lab_id,
            "name": name,
            "age": patient.age,
            "sex": patient.sex,
            "created_at": patient.created_at
        }

    def list_patients(self, skip: int=0, limit: int=50) -> List[dict]:
        patients = self.repo.get_all(skip, limit)
        results = []
        for p in patients:
            try:
                name = crypto.crypto.decrypt(p.encrypted_name)
            except:
                name = "Error"
            results.append({
                "id": p.id,
                "lab_id": p.lab_id,
                "name": name,
                "age": p.age,
                "sex": p.sex
            })
        return results

class ScreeningService:
    def __init__(self, db: Session, org_id: UUID):
        self.repo = BaseRepository(Screening, db, org_id)
        self.patient_repo = BaseRepository(Patient, db, org_id)
        self.org_id = org_id

    async def create_screening(self, patient_id: UUID, cbc_data: dict) -> Screening:
        # 1. Verify Patient
        patient = self.patient_repo.get(patient_id)
        if not patient:
            raise ValueError("Patient not found")

        # 2. Run ML (Async)
        # This will raise if ML engine is not ready (Fail Closed)
        risk, conf = await engine.predict(cbc_data)
        
        # 3. Create Record
        screening = Screening(
            patient_id=patient_id,
            org_id=self.org_id,
            hemoglobin=float(cbc_data.get("hb", 0)),
            mcv=float(cbc_data.get("mcv", 0)),
            risk_class=risk.value,
            confidence_score=conf,
            model_version=engine.model_version,
            input_hash="TODO_HASH", 
            raw_panel_encrypted=cbc_data # Should encrypt this too ideally
        )
        return self.repo.create(screening)

    def get_screening(self, screening_id: UUID) -> Optional[Screening]:
        return self.repo.get(screening_id)
        
    def list_by_patient(self, patient_id: UUID) -> List[Screening]:
        return self.repo.db.exec(
            select(Screening)
            .where(Screening.patient_id == patient_id)
            .where(Screening.org_id == self.org_id)
        ).all()
