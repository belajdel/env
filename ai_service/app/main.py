"""
AI Service Main Application
FastAPI app for ML inference and model management
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_database, close_mongo_connection
from app.core.logging import setup_logging, get_logger
from app.api import routes as api_routes
from app.services.retraining import init_scheduler, shutdown_scheduler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("starting_ai_service", version=settings.APP_VERSION)
    
    # Initialize database
    await init_database()
    logger.info("database_initialized")
    
    # Generate synthetic data if no training data exists
    try:
        db = init_database.__globals__["get_database"]()
        count = await db["training_data"].count_documents({})
        if count == 0:
            logger.info("no_training_data_generating_synthetic")
            from app.services.data_generator import generate_and_save_synthetic_data
            generate_and_save_synthetic_data()
            logger.info("synthetic_data_generated_on_startup")
    except Exception as e:
        logger.warning("startup_data_check_failed", error=str(e))
    
    # Initialize retraining scheduler
    await init_scheduler()
    
    yield
    
    # Shutdown
    logger.info("shutting_down_ai_service")
    await shutdown_scheduler()
    await close_mongo_connection()
    logger.info("database_closed")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Environmental Monitoring AI Service - Anomaly Detection, Predictions, Risk Scoring",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Include routes
app.include_router(api_routes.router, prefix="/api/v1")


# Global exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )


@app.get("/", summary="Service info")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_config=None,
    )