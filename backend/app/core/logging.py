"""
Structured Logging Configuration
Uses structlog for JSON logging with context.
"""

import logging
import sys
from typing import Any, Dict

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add application context to log entries."""
    event_dict["app"] = settings.APP_NAME
    event_dict["version"] = settings.APP_VERSION
    return event_dict


def drop_debug_logs(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Drop debug logs in production."""
    if not settings.DEBUG and event_dict.get("level") == "debug":
        raise structlog.DropEvent
    return event_dict


def setup_logging() -> None:
    """Configure structlog for the application."""
    
    # Standard library logging configuration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )
    
    # Processors for structlog
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_app_context,
        drop_debug_logs,
    ]
    
    if settings.DEBUG:
        # Pretty console output for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # JSON output for production
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


# Context variables for request tracing
import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")
zone_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("zone_id", default="")


def bind_request_context(request_id: str, user_id: str = "", zone_id: str = "") -> None:
    """Bind request context variables."""
    request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)
    if zone_id:
        zone_id_var.set(zone_id)


def clear_request_context() -> None:
    """Clear request context variables."""
    request_id_var.set("")
    user_id_var.set("")
    zone_id_var.set("")


class RequestLoggingMiddleware:
    """Middleware to add request context to logs."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        import uuid
        request_id = str(uuid.uuid4())[:8]
        bind_request_context(request_id)
        
        structlog.contextvars.bind_contextvars(request_id=request_id)
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                structlog.contextvars.bind_contextvars(
                    status_code=message.get("status"),
                )
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            clear_request_context()
            structlog.contextvars.clear_contextvars()


# Initialize logging on import
setup_logging()