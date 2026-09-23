from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from backend.core.config import settings
    from backend.api.router import router as api_router
except ModuleNotFoundError:
    from core.config import settings
    from api.router import router as api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for ICVER (Informal Worker Income Verification System)",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include main API router with version prefix
app.include_router(api_router, prefix=settings.API_V1_STR, tags=["Income Verification & Consent"])


@app.get("/", tags=["Root"])
async def root():
    return {
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "icver-backend"
    }
