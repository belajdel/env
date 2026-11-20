"""
FastAPI Application Entry Point
Environmental Monitoring Backend API
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.database import init_database, close_mongo_connection, get_database, Collections
from app.core.logging import get_logger, setup_logging, RequestLoggingMiddleware
from app.api import (
    auth_router, users_router, zones_router, devices_router,
    measurements_router, alerts_router, alert_rules_router,
    reports_router, audit_router, ai_router, relay_router, health_router,
    websocket_router
)
from app.services.mqtt_ingestion import get_mqtt_service
from app.services.websocket import get_websocket_manager
from app.services.auth import get_auth_service, TokenData
from app.services.rbac import get_rbac_service, Permission, ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST

logger = get_logger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("starting_application", version=settings.APP_VERSION)
    
    # Initialize database
    await init_database()
    logger.info("database_initialized")
    
    # Start MQTT ingestion
    mqtt_service = get_mqtt_service()
    await mqtt_service.start()
    logger.info("mqtt_ingestion_started")
    
    # Start WebSocket manager
    ws_manager = get_websocket_manager()
    await ws_manager.start()
    logger.info("websocket_manager_started")
    
    yield
    
    # Shutdown
    logger.info("shutting_down_application")
    
    # Stop WebSocket manager
    await ws_manager.stop()
    logger.info("websocket_manager_stopped")
    
    # Stop MQTT ingestion
    await mqtt_service.stop()
    logger.info("mqtt_ingestion_stopped")
    
    # Close database
    await close_mongo_connection()
    logger.info("database_closed")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Industrial Environmental Monitoring Platform API",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)


# Authentication dependency
async def get_current_user(
    request: Request,
    auth=Depends(get_auth_service),
) -> TokenData:
    """Extract and verify JWT token from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_header[7:]  # Remove "Bearer "
    try:
        return auth.verify_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


# Permission dependencies
def require_permission(permission: Permission):
    """Create dependency that checks permission."""
    async def check_permission(
        token_data: TokenData = Depends(get_current_user),
        rbac=Depends(get_rbac_service),
    ):
        if not rbac.has_permission(token_data.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required"
            )
        return token_data
    return check_permission


def require_zone_permission(permission: Permission):
    """Create dependency that checks permission + zone access from path param."""
    async def check_permission(
        request: Request,
        token_data: TokenData = Depends(get_current_user),
        rbac=Depends(get_rbac_service),
    ):
        # Extract zone_id from path parameters
        zone_id = request.path_params.get("zone_id")
        if not zone_id:
            raise HTTPException(400, "Zone ID not found in path")
        
        if not rbac.check_permission(token_data.role, permission, zone_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required for zone {zone_id}"
            )
        return token_data
    return check_permission


# Role-based dependencies
def require_role(*roles: str):
    """Create dependency that checks role."""
    async def check_role(
        token_data: TokenData = Depends(get_current_user),
    ):
        if token_data.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {', '.join(roles)}"
            )
        return token_data
    return check_role


# Apply auth dependencies to routes
# We'll use a simpler approach: include routers and apply dependencies at route level

# Include routers
app.include_router(health_router)

# Auth routes (no auth required)
app.include_router(auth_router)

# Protected routes with authentication
# Users - admin only
app.include_router(
    users_router,
    dependencies=[Depends(get_current_user), Depends(require_role(ROLE_ADMIN))],
)

# Zones - read for all authenticated, write for admin/operator
app.include_router(
    zones_router,
    dependencies=[Depends(get_current_user)],
)

# Devices - read for all, write for admin/operator
app.include_router(
    devices_router,
    dependencies=[Depends(get_current_user)],
)

# Measurements - read for all authenticated
app.include_router(
    measurements_router,
    dependencies=[Depends(get_current_user)],
)

# Alerts - read for all, acknowledge/resolve for operator+
app.include_router(
    alerts_router,
    dependencies=[Depends(get_current_user)],
)

# Alert rules - read for all, write for admin/operator
app.include_router(
    alert_rules_router,
    dependencies=[Depends(get_current_user)],
)

# Reports - create/read for operator+, download for operator+
app.include_router(
    reports_router,
    dependencies=[Depends(get_current_user)],
)

# Audit - admin only
app.include_router(
    audit_router,
    dependencies=[Depends(get_current_user), Depends(require_role(ROLE_ADMIN))],
)

# AI - predict/anomaly/risk for operator+, retrain for admin
app.include_router(
    ai_router,
    dependencies=[Depends(get_current_user)],
)

# Relay - control for operator/maintenance/admin
app.include_router(
    relay_router,
    dependencies=[Depends(get_current_user), Depends(require_role(ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE))],
)

# WebSocket - real-time data (authenticated via token query param)
app.include_router(websocket_router)


# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": f"HTTP_{exc.status_code}"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )


# Root endpoint
@app.get("/", summary="API Root")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else "disabled",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_config=None,  # Use structlog
    )