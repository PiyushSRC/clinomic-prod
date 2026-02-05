from sqlmodel import SQLModel, create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create Engine
# pool_pre_ping=True prevents connection drop issues
engine = create_engine(
    str(settings.DATABASE_URL),
    pool_pre_ping=True,
    echo=(settings.APP_ENV == "dev")
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
