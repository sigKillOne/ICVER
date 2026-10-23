from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from backend.core.config import settings
    from backend.api.router import router as api_router, is_ml_ready
except ModuleNotFoundError:
    from core.config import settings
    from api.router import router as api_router, is_ml_ready

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for ICVER (Informal Worker Income Verification System)",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set up CORS middleware using settings.CORS_ORIGINS
# Never combine allow_origins=["*"] with allow_credentials=True
cors_origins = list(settings.CORS_ORIGINS)
allow_creds = False if ("*" in cors_origins) else True

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include main API router with version prefix
app.include_router(api_router, prefix=settings.API_V1_STR, tags=["Income Verification & Consent"])


@app.get("/", tags=["Root"])
def root():
    return {
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
def health_check():
    models_ready = is_ml_ready()
    return {
        "status": "healthy" if models_ready else "degraded",
        "service": "icver-backend",
        "model_status": {
            "models_loaded": models_ready
        }
    }
