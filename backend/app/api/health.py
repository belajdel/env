"""
Health Check Endpoints
"""

from fastapi import APIRouter, Depends
from pymongo.errors import PyMongoError

from app.core.config import settings
from app.core.database import get_database, Collections
from app.services.mqtt_ingestion import get_mqtt_service
from app.services.ai_client import get_ai_client

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@router.get("/health/detailed", summary="Detailed health check")
async def detailed_health_check():
    """Detailed health check with dependency status."""
    db = get_database()
    mqtt_service = get_mqtt_service()
    ai_client = get_ai_client()
    
    checks = {}
    
    # Database
    try:
        await db.command("ping")
        checks["database"] = {"status": "healthy", "details": "Connected"}
    except PyMongoError as e:
        checks["database"] = {"status": "unhealthy", "details": str(e)}
    
    # MQTT
    mqtt_stats = mqtt_service.get_stats()
    checks["mqtt"] = {
        "status": "healthy" if mqtt_stats["connected"] else "unhealthy",
        "details": f"Connected: {mqtt_stats['connected']}, Messages: {mqtt_stats['messages_received']}",
    }
    
    # AI Service
    ai_healthy = await ai_client.health_check()
    checks["ai_service"] = {
        "status": "healthy" if ai_healthy else "unhealthy",
        "details": f"Enabled: {ai_client.enabled}, URL: {ai_client.base_url}",
    }
    
    # Overall status
    all_healthy = all(c["status"] == "healthy" for c in checks.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "checks": checks,
    }


@router.get("/health/ready", summary="Readiness probe")
async def readiness_check():
    """Kubernetes readiness probe."""
    db = get_database()
    
    try:
        await db.command("ping")
        return {"status": "ready"}
    except PyMongoError:
        return {"status": "not ready", "reason": "Database unavailable"}, 503


@router.get("/health/live", summary="Liveness probe")
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive"}