"""
Pytest Configuration for Backend Tests
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import Settings
from app.models.user import UserInDB, UserPublic, ROLE_ADMIN, ROLE_OPERATOR
from app.models.zone import ZoneInDB
from app.models.device import DeviceInDB
from app.models.measurement import MeasurementCreate
from app.models.alert import AlertRuleInDB, AlertInDB, AlertLevel, AlertStatus


# Test settings
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings."""
    return Settings(
        MONGO_URI="mongodb://localhost:27017",
        MONGO_DB="env_monitoring_test",
        JWT_SECRET_KEY="test-secret-key-for-testing-only",
        JWT_ALGORITHM="HS256",
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30,
        JWT_REFRESH_TOKEN_EXPIRE_DAYS=7,
        MQTT_BROKER="localhost",
        MQTT_PORT=8883,
        MQTT_USE_TLS=False,
        AI_SERVICE_ENABLED=False,
        DEBUG=True,
        LOG_LEVEL="DEBUG",
    )


# Event loop
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Mock database
@pytest.fixture
def mock_db():
    """Mock database for unit tests."""
    db = AsyncMock()
    db.command = AsyncMock(return_value={"ok": 1})
    return db


# Mock user
@pytest.fixture
def admin_user() -> UserInDB:
    """Admin user for testing."""
    return UserInDB(
        username="admin",
        email="admin@test.com",
        full_name="Test Admin",
        role=ROLE_ADMIN,
        is_active=True,
        password_hash="$2b$12$testhash",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def operator_user() -> UserInDB:
    """Operator user for testing."""
    return UserInDB(
        username="operator",
        email="operator@test.com",
        full_name="Test Operator",
        role=ROLE_OPERATOR,
        is_active=True,
        password_hash="$2b$12$testhash",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# Mock zone
@pytest.fixture
def test_zone() -> ZoneInDB:
    """Test zone."""
    return ZoneInDB(
        zone_id="prod-01",
        name="Production Line 1",
        type="production",
        location="Building A",
        description="Test zone",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# Mock alert rule
@pytest.fixture
def test_alert_rule() -> AlertRuleInDB:
    """Test alert rule."""
    return AlertRuleInDB(
        zone_id="prod-01",
        parameter="temperature",
        warning_min=18.0,
        warning_max=28.0,
        critical_min=15.0,
        critical_max=35.0,
        min_duration_sec=60,
        correlation_rules=[],
        enabled=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# Mock measurement
@pytest.fixture
def test_measurement() -> MeasurementCreate:
    """Test measurement."""
    return MeasurementCreate(
        zone_id="prod-01",
        parameter="temperature",
        value=36.0,
        unit="°C",
        timestamp=datetime.now(timezone.utc),
    )


# Mock alert
@pytest.fixture
def test_alert() -> AlertInDB:
    """Test alert."""
    return AlertInDB(
        zone_id="prod-01",
        parameter="temperature",
        level=AlertLevel.CRITICAL,
        value=36.0,
        threshold=35.0,
        unit="°C",
        message="CRITICAL: Temperature in prod-01 is 36.0°C (threshold: 35.0°C)",
        status=AlertStatus.OPEN,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# Async test helpers
@pytest.fixture
def mock_websocket():
    """Mock WebSocket for testing."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


# Patch external services
@pytest.fixture(autouse=True)
def patch_external_services():
    """Patch external services for unit tests."""
    with patch("app.services.mqtt_ingestion.get_mqtt_service") as mock_mqtt, \
         patch("app.services.ai_client.get_ai_client") as mock_ai, \
         patch("app.services.websocket.get_websocket_manager") as mock_ws, \
         patch("app.core.database.get_database") as mock_get_db:
        
        # Configure mocks
        mock_mqtt.return_value = AsyncMock()
        mock_mqtt.return_value.start = AsyncMock()
        mock_mqtt.return_value.stop = AsyncMock()
        mock_mqtt.return_value.get_stats = MagicMock(return_value={})
        
        mock_ai.return_value = AsyncMock()
        mock_ai.return_value.enabled = False
        mock_ai.return_value.health_check = AsyncMock(return_value=False)
        
        mock_ws.return_value = AsyncMock()
        mock_ws.return_value.start = AsyncMock()
        mock_ws.return_value.stop = AsyncMock()
        mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
        mock_ws.return_value.broadcast_alert_update = AsyncMock(return_value=0)
        mock_ws.return_value.get_stats = MagicMock(return_value={})
        
        yield {
            "mqtt": mock_mqtt,
            "ai": mock_ai,
            "ws": mock_ws,
            "db": mock_get_db,
        }