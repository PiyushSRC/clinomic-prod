from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.api import api_router
from app.ml.loader import init_ml

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.on_event("startup")
def startup_event():
    # Load ML models safety
    init_ml()

@app.get("/health")
def health_check():
    from app.ml.engine import engine
    if not engine.ready:
        # 503 if ML critical path is down? 
        # Or just return status. Spec said "Explicit READY state".
        return {"status": "warning", "ml_ready": False, "version": "2.0.0"}
    return {"status": "ok", "ml_ready": True, "version": "2.0.0"}

app.include_router(api_router, prefix=settings.API_V1_STR)
