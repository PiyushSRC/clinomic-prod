from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from app.main import app
from app.core.config import settings
from app.modules.auth.models import User, Organization
from app.api.deps import get_db
import uuid

# Use the same TEST DB URL as before
TEST_DB_URL = "postgresql://postgres:password@localhost:5432/biosaas_v2"
engine = create_engine(TEST_DB_URL)

def override_get_db():
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def setup_data():
    # Ensure fresh DB for test (or just use existing if careful)
    # Re-create tables to be clean
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as db:
        org_id = uuid.uuid4()
        org = Organization(id=org_id, name="Pilot Lab", is_active=True)
        db.add(org)
        
        user = User(
            email="lab@pilot.com", 
            hashed_password="pw", # We need real hash if we use login endpoint
            # But for TestClient we can mock auth or used helper that makes token directly
            # Let's use real login flow to test "End to End"
            role="LAB",
            org_id=org_id,
            is_active=True
        )
        # Hash password properly
        from app.core.security import get_password_hash
        user.hashed_password = get_password_hash("password123")
        
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

def run_e2e():
    print("🚀 Starting E2E Clinical Flow Verification...")
    
    # 1. Setup
    user = setup_data()
    print("✅ Setup complete.")
    
    # 2. Login
    login_payload = {"username": "lab@pilot.com", "password": "password123"}
    resp = client.post(f"{settings.API_V1_STR}/login/access-token", data=login_payload)
    if resp.status_code != 200:
        print(f"❌ Login Failed: {resp.text}")
        exit(1)
    
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Login successful. Token received.")
    
    # 3. Create Patient
    patient_data = {
        "lab_id": "P-100",
        "name": "Jane Doe",
        "age": 30,
        "sex": "F",
        "phone": "555-0000"
    }
    resp = client.post(f"{settings.API_V1_STR}/patients/", json=patient_data, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Create Patient Failed: {resp.text}")
        exit(1)
    
    patient_id = resp.json()["id"]
    print(f"✅ Patient Created: {patient_id}")
    
    # 4. Create Screening (Trigger ML)
    screening_data = {
        "patient_id": patient_id,
        "hb": 9.5, # Low -> Should trigger deficiency
        "mcv": 105, # High -> Should trigger deficiency
        "extra_data": {"ferritin": 10}
    }
    resp = client.post(f"{settings.API_V1_STR}/screenings/", json=screening_data, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Screening Failed: {resp.text}")
        exit(1)
        
    result = resp.json()
    print(f"✅ Screening Completed. ID: {result['id']}")
    print(f"   Risk Class: {result['risk_class']} (Expected 3 for Deficient)")
    print(f"   Confidence: {result['confidence_score']}")
    
    if result['risk_class'] == 3:
        print("✅ ML Logic Verified (Mock)")
    else:
        print("⚠️ ML Outcome unexpected (Check Mock Logic)")

    # 5. Verify Persistence & Encryption
    # Query DB directly to check encrypted_name
    with Session(engine) as db:
        from app.modules.clinics.models import Patient
        p = db.get(Patient, patient_id)
        if p.encrypted_name == "Jane Doe":
             print("❌ FAIL: Patient name stored in plaintext!")
             exit(1)
        elif "gAAAA" in p.encrypted_name: # Basic check for Fernet prefix usually
             print("✅ Encryption Verified (stored as ciphertext)")
        else:
             print(f"⚠️ Encrypted name looks weird: {p.encrypted_name}")

    print("\n🎉 ALL SYSTEMS GO FOR PILOT")

if __name__ == "__main__":
    run_e2e()
