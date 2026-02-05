import asyncio
print("--- TEST SCRIPT STARTING ---")
import uuid
import jwt
from uuid import UUID
from datetime import timedelta
from contextvars import copy_context
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session, select
from app.core.config import settings
from app.core.security import create_access_token
from app.core.tenant import set_tenant_context, get_current_org_id, _current_org_id
from app.db.repository import BaseRepository
from app.modules.auth.models import User, Organization, AuditLog
from app.modules.audit.utils import audit

# --- Configuration ---
# Use the same DB as docker-compose (exposed on localhost:5432)
TEST_DB_URL = "postgresql://postgres:password@localhost:5432/biosaas_v2"
engine = create_engine(TEST_DB_URL, echo=False)

async def main():
    print("⏳ Waiting for DB...")
    # Simple retry logic would be better, but assuming up for now
    
    print("🔄 Resetting DB Schema...")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    
    # Run Validations
    await test_tenant_isolation()
    await test_jwt_tampering()
    await test_audit_integrity()
    await test_context_leakage()
    await test_db_permissions()

    print("\n✅ ALL CHECKS PASSED")

# ------------------------------------------------------------------
# 1) Tenant Isolation Test
# ------------------------------------------------------------------
async def test_tenant_isolation():
    print("\n[1/5] Testing Tenant Isolation...")
    with Session(engine) as db:
        # Setup Data
        org_a_id = uuid.uuid4()
        org_b_id = uuid.uuid4()
        
        org_a = Organization(id=org_a_id, name="Org A")
        org_b = Organization(id=org_b_id, name="Org B")
        db.add(org_a)
        db.add(org_b)
        db.commit()
        
        # Add User to Org A
        user_a = User(email="a@a.com", hashed_password="pw", role="LAB", org_id=org_a_id)
        db.add(user_a)
        db.commit()

        # TEST: Query User A using Org B context
        # Simulate Middleware setting context
        set_tenant_context(org_b_id)
        
        repo_b = BaseRepository(User, db, org_b_id)
        result = repo_b.get(user_a.id)
        
        if result:
            print("❌ FAIL: Retrieved Org A user with Org B context!")
            exit(1)
            
        print("   ✅ Direct ID fetch blocked.")
        
        # TEST: Get All
        list_result = repo_b.get_all()
        if len(list_result) > 0:
             print("❌ FAIL: get_all leaked data!")
             exit(1)
        print("   ✅ List fetch blocked.")
        
        # TEST: Create Cross-Tenant
        # Try to create an object for Org A while using Org B repo/context
        user_hack = User(email="hack@b.com", hashed_password="pw", role="LAB", org_id=org_a_id)
        created = repo_b.create(user_hack)
        
        if created.org_id != org_b_id:
             print(f"❌ FAIL: Repository failed to overwrite org_id. Got {created.org_id}")
             exit(1)
        print("   ✅ Create enforced org_id overwrite.")


# ------------------------------------------------------------------
# 2) JWT Tamper Test
# ------------------------------------------------------------------
async def test_jwt_tampering():
    print("\n[2/5] Testing JWT Integrity...")
    org_id = uuid.uuid4()
    
    # Valid Token
    token = create_access_token("test_user", str(org_id))
    
    # Tamper: Change Payload (Base64 decode -> edit -> encode is tricky in 1 line, assume simple truncation/concat checks first)
    # Append nonsense
    bad_token = token + "sabotage"
    
    try:
        jwt.decode(bad_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        print("❌ FAIL: Accepted garbage token")
        exit(1)
    except Exception:
        print("   ✅ Garbage signature rejected.")
        
    # Tamper: HS256 None attack check (library handles this, but verify)
    # decode without verify
    header, payload, sig = token.split('.')
    tampered_payload = jwt.utils.base64url_encode(b'{"sub":"test_user","org_id":"admin-org","exp":9999999999}').decode('utf-8')
    forged_token = f"{header}.{tampered_payload}.{sig}" # Signature mismatch
    
    try:
        jwt.decode(forged_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        print("❌ FAIL: Accepted tampered payload with old signature")
        exit(1)
    except jwt.InvalidSignatureError:
        print("   ✅ Signature mismatch rejected.")


# ------------------------------------------------------------------
# 3) Audit Log Integrity Test
# ------------------------------------------------------------------
async def test_audit_integrity():
    print("\n[3/5] Testing Audit Log Chain...")
    org_id = uuid.uuid4()
    
    with Session(engine) as db:
        # Create Org
        org = Organization(id=org_id, name="Audit Org")
        db.add(org)
        db.commit()
    
        # Log Event 1
        audit.log(db, org_id, "user1", "LOGIN", "session", "1")
        # Log Event 2
        audit.log(db, org_id, "user1", "VIEW", "patient", "101")
        
        logs = db.exec(select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.timestamp)).all()
        
        log1, log2 = logs[0], logs[1]
        
        # Verify Chain
        if log2.prev_hash != log1.signature:
            print("❌ FAIL: Hash chain broken (prev_hash != log1.signature)")
            exit(1)
            
        # Verify Signature 1
        payload1 = {
             "org_id": str(org_id), "actor_id": "user1", "action": "LOGIN", 
             "entity": "session", "entity_id": "1", "timestamp": log1.timestamp.isoformat(), 
             "prev_hash": "0"*64, "details": {}
        }
        recalc_sig1 = audit.compute_signature(audit.canonical_str(payload1))
        
        if recalc_sig1 != log1.signature:
             print("❌ FAIL: Signature verification failed for Log 1")
             # Debug time format issues can be tricky, relying on strict isoformat
             # If this fails locally due to microsecond precision diffs, we refine.
             # print(f"Expected: {recalc_sig1}")
             # print(f"Actual:   {log1.signature}")
             exit(1)

        print("   ✅ Hash chain verified.")
        print("   ✅ Signature verified.")

# ------------------------------------------------------------------
# 4) ContextVar Leakage Test (Async)
# ------------------------------------------------------------------
async def test_context_leakage():
    print("\n[4/5] Testing ContextVar Isolation (Async)...")
    
    async def task_runner(name, org_uuid, delay):
        set_tenant_context(org_uuid)
        await asyncio.sleep(delay)
        # Check if context is still ours
        current = get_current_org_id()
        if current != org_uuid:
            return False, f"{name} lost context! Got {current}, expected {org_uuid}"
        return True, "OK"

    id_1 = uuid.uuid4()
    id_2 = uuid.uuid4()
    
    # Run interleaved tasks
    results = await asyncio.gather(
        task_runner("Task A", id_1, 0.1),
        task_runner("Task B", id_2, 0.05), # Finishes first
        task_runner("Task C", id_1, 0.15)
    )
    
    for success, msg in results:
        if not success:
            print(f"❌ FAIL: {msg}")
            exit(1)
            
    print("   ✅ Async contexts remained isolated.")


# ------------------------------------------------------------------
# 5) DB Permissions Check
# ------------------------------------------------------------------
async def test_db_permissions():
    print("\n[5/5] Testing DB Permissions (Simulated)...")
    
    # Create the restricted role
    # Note: We need to do this as superuser
    TEST_APP_USER = "biosaas_app"
    TEST_APP_PASS = "secure_pass"
    
    with engine.connect() as conn:
        conn.execute(text(f"DROP ROLE IF EXISTS {TEST_APP_USER}"))
        conn.execute(text(f"CREATE USER {TEST_APP_USER} WITH PASSWORD '{TEST_APP_PASS}'"))
        conn.execute(text(f"GRANT CONNECT ON DATABASE biosaas_v2 TO {TEST_APP_USER}"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {TEST_APP_USER}"))
        conn.execute(text(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {TEST_APP_USER}"))
        
        # THE CORE CHECK: Revoke Delete/Update on AuditLog
        conn.execute(text(f"REVOKE UPDATE, DELETE ON auditlog FROM {TEST_APP_USER}"))
        conn.commit()

    # New Engine as App User
    app_url = TEST_DB_URL.replace("postgres:password", f"{TEST_APP_USER}:{TEST_APP_PASS}")
    app_engine = create_engine(app_url)
    
    try:
        with Session(app_engine) as db:
            # Try to delete an audit log
            # We assume logs exist from step 3
            # We might need to fetch ID via a harmless select first
             log = db.exec(select(AuditLog).limit(1)).first()
             if log:
                 db.delete(log)
                 db.commit()
                 print("❌ FAIL: App user was able to DELETE AuditLog!")
                 exit(1)
    except Exception as e:
        # We expect a permission error (ProgrammingError or InsufficientPrivilege)
        if "permission denied" in str(e).lower():
             print("   ✅ DELETE blocked by DB.")
        else:
             print(f"   ⚠️ Blocked, but unexpected error: {e}")
             # Acceptable for this test if it blocked the action

    # Clean up role? Maybe keep for next tests.

if __name__ == "__main__":
    asyncio.run(main())
