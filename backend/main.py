from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from backend.core import risk_v2
    from backend.core.config import settings
    from backend.api.router import router as api_router, is_ml_ready
    from backend.api.verify_router import router as verify_router
except ModuleNotFoundError:
    from core import risk_v2
    from core.config import settings
    from api.router import router as api_router, is_ml_ready
    from api.verify_router import router as verify_router

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


@app.exception_handler(RequestValidationError)
async def redact_validation_inputs(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return validation details without echoing request values such as SMS text."""
    safe_errors = []
    for error in exc.errors():
        safe_errors.append(
            {
                key: value
                for key, value in error.items()
                if key not in {"input", "ctx"}
            }
        )
    return JSONResponse(status_code=422, content={"detail": safe_errors})


# Include main API router with version prefix
app.include_router(api_router, prefix=settings.API_V1_STR, tags=["Income Verification & Consent"])
app.include_router(verify_router, prefix=settings.API_V1_STR, tags=["Verification & Risk"])


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
    risk_status = risk_v2.health()
    return {
        "status": "healthy" if models_ready else "degraded",
        "service": "icver-backend",
        "model_status": {
            "models_loaded": models_ready
        },
        "risk_v2": risk_status,
    }
