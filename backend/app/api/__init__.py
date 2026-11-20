"""
API Routes Package
"""

from .auth import router as auth_router
from .users import router as users_router
from .zones import router as zones_router
from .devices import router as devices_router
from .measurements import router as measurements_router
from .alerts import router as alerts_router
from .alert_rules import router as alert_rules_router
from .reports import router as reports_router
from .audit import router as audit_router
from .ai import router as ai_router
from .relay import router as relay_router
from .health import router as health_router
from .websocket import router as websocket_router

__all__ = [
    "auth_router", "users_router", "zones_router", "devices_router",
    "measurements_router", "alerts_router", "alert_rules_router",
    "reports_router", "audit_router", "ai_router", "relay_router", "health_router",
    "websocket_router",
]