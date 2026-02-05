import logging
import sys
import os

# Add parent directory to path to allow importing app
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlmodel import Session, select
from app.db.session import engine # Import engine directly
from app.modules.auth.models import User, Organization
from app.core.security import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_db():
    # Use SQLModel Session context manager
    with Session(engine) as db:
        try:
            # 1. Check/Create Organization
            org_name = "Test Lab"
            org = db.exec(select(Organization).where(Organization.name == org_name)).first()
            if not org:
                logger.info(f"Creating Organization: {org_name}")
                org = Organization(name=org_name, is_active=True)
                db.add(org)
                db.commit()
                db.refresh(org)
            else:
                logger.info(f"Organization '{org_name}' already exists.")

            # 2. Check/Create Admin User
            admin_email = "admin@test.com"
            user = db.exec(select(User).where(User.email == admin_email)).first()
            if not user:
                logger.info(f"Creating User: {admin_email}")
                user = User(
                    email=admin_email,
                    hashed_password=get_password_hash("Admin123!"),
                    role="ADMIN",
                    is_active=True,
                    org_id=org.id, # Using ID from Organization object
                    full_name="System Admin"
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                
                print("\n" + "="*30)
                print("✅ Admin User Created")
                print(f"Email:    {admin_email}")
                print("Password: Admin123!")
                print("="*30 + "\n")
            else:
                logger.info(f"User '{admin_email}' already exists.")
                print("\n✅ Seed check complete. User already exists.\n")

        except Exception as e:
            logger.error(f"Error seeding database: {e}")
            raise

if __name__ == "__main__":
    seed_db()
