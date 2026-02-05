from fastapi import APIRouter
from app.api.v1.endpoints import auth, patients, screenings

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(screenings.router, prefix="/screenings", tags=["screenings"])
