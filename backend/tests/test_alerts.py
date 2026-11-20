"""
Alert Engine Tests
Includes latency test for critical path (<420ms budget).
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.alerts import (
    AlertEngine, AlertState, AlertTracking, get_alert_engine
)
from app.models.alert import (
    AlertRuleInDB, AlertInDB, AlertPublic, AlertLevel, AlertStatus, VALID_PARAMETERS
)
from app.models.measurement import MeasurementCreate


class TestAlertEngine:
    """Test alert engine logic."""
    
    @pytest.fixture
    def alert_engine(self):
        """Fresh alert engine for each test."""
        engine = AlertEngine()
        # Clear any cached state
        engine._tracking.clear()
        engine._rules_cache.clear()
        engine._last_rules_update = None
        return engine
    
    @pytest.fixture
    def temperature_rule(self):
        """Temperature alert rule for prod-01."""
        return AlertRuleInDB(
            zone_id="prod-01",
            parameter="temperature",
            warning_min=18.0,
            warning_max=28.0,
            critical_min=15.0,
            critical_max=35.0,
            min_duration_sec=60,
            correlation_rules=["humidity"],
            enabled=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    
    @pytest.fixture
    def humidity_rule(self):
        """Humidity alert rule for prod-01."""
        return AlertRuleInDB(
            zone_id="prod-01",
            parameter="humidity",
            warning_min=30.0,
            warning_max=70.0,
            critical_min=20.0,
            critical_max=85.0,
            min_duration_sec=60,
            correlation_rules=["temperature"],
            enabled=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    
    def test_threshold_check(self, alert_engine):
        """Test threshold checking."""
        # Value within range
        assert not alert_engine._check_threshold(25.0, 18.0, 28.0)
        assert not alert_engine._check_threshold(20.0, 18.0, 28.0)
        
        # Value exceeds max
        assert alert_engine._check_threshold(30.0, 18.0, 28.0)
        assert alert_engine._check_threshold(28.0, 18.0, 28.0)  # boundary
        
        # Value below min
        assert alert_engine._check_threshold(15.0, 18.0, 28.0)
        assert alert_engine._check_threshold(18.0, 18.0, 28.0)  # boundary
        
        # Only max threshold
        assert alert_engine._check_threshold(100.0, None, 50.0)
        assert not alert_engine._check_threshold(30.0, None, 50.0)
        
        # Only min threshold
        assert alert_engine._check_threshold(5.0, 10.0, None)
        assert not alert_engine._check_threshold(15.0, 10.0, None)
        
        # No thresholds
        assert not alert_engine._check_threshold(100.0, None, None)
    
    @pytest.mark.asyncio
    async def test_critical_alert_creation(self, alert_engine, temperature_rule):
        """Test critical alert is created immediately."""
        # Mock database
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=None)  # No existing alert
            mock_collection.insert_one = AsyncMock()
            mock_collection.update_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            
            # Inject rule into cache
            alert_engine._rules_cache["prod-01:temperature"] = temperature_rule
            
            # Create measurement exceeding critical threshold
            measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="temperature",
                value=36.0,
                unit="°C",
                timestamp=datetime.now(timezone.utc),
            )
            
            alerts = await alert_engine.check_measurement(measurement)
            
            assert len(alerts) == 1
            assert alerts[0].level == "critical"
            assert alerts[0].status == "pending"
            assert alerts[0].value == 36.0
            assert alerts[0].threshold == 35.0
    
    @pytest.mark.asyncio
    async def test_warning_alert_creation(self, alert_engine, temperature_rule):
        """Test warning alert creation."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=None)
            mock_collection.insert_one = AsyncMock()
            mock_collection.update_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            
            alert_engine._rules_cache["prod-01:temperature"] = temperature_rule
            
            # Create measurement in warning range
            measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="temperature",
                value=30.0,
                unit="°C",
                timestamp=datetime.now(timezone.utc),
            )
            
            alerts = await alert_engine.check_measurement(measurement)
            
            assert len(alerts) == 1
            assert alerts[0].level == "warning"
            assert alerts[0].status == "pending"
    
    @pytest.mark.asyncio
    async def test_no_alert_in_normal_range(self, alert_engine, temperature_rule):
        """Test no alert when value is normal."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            
            alert_engine._rules_cache["prod-01:temperature"] = temperature_rule
            
            measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="temperature",
                value=22.0,
                unit="°C",
                timestamp=datetime.now(timezone.utc),
            )
            
            alerts = await alert_engine.check_measurement(measurement)
            
            assert len(alerts) == 0
    
    @pytest.mark.asyncio
    async def test_alert_deduplication(self, alert_engine, temperature_rule):
        """Test duplicate alerts are not created."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            # First call - no existing alert
            existing_alert = {
                "_id": "alert123",
                "zone_id": "prod-01",
                "parameter": "temperature",
                "level": "critical",
                "value": 36.0,
                "threshold": 35.0,
                "unit": "°C",
                "message": "CRITICAL...",
                "status": "open",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=existing_alert)
            mock_collection.update_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            
            alert_engine._rules_cache["prod-01:temperature"] = temperature_rule
            
            measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="temperature",
                value=37.0,
                unit="°C",
                timestamp=datetime.now(timezone.utc),
            )
            
            alerts = await alert_engine.check_measurement(measurement)
            
            # Should update existing alert, not create new
            assert len(alerts) == 1
            assert alerts[0].id == "alert123"
            assert alerts[0].value == 37.0
            mock_collection.update_one.assert_called()
            mock_collection.insert_one.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_correlation_escalation(self, alert_engine, temperature_rule, humidity_rule):
        """Test correlation escalates warning to critical."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=None)
            mock_collection.insert_one = AsyncMock()
            mock_collection.update_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            mock_ws.return_value.broadcast_alert_update = AsyncMock(return_value=0)
            
            alert_engine._rules_cache["prod-01:temperature"] = temperature_rule
            alert_engine._rules_cache["prod-01:humidity"] = humidity_rule
            
            # First, create active critical alert for humidity
            humidity_measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="humidity",
                value=90.0,
                unit="%",
                timestamp=datetime.now(timezone.utc),
            )
            await alert_engine.check_measurement(humidity_measurement)
            
            # Now check temperature in warning range - should escalate to critical
            temp_measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="temperature",
                value=30.0,
                unit="°C",
                timestamp=datetime.now(timezone.utc),
            )
            alerts = await alert_engine.check_measurement(temp_measurement)
            
            # Should create critical alert due to correlation
            assert len(alerts) >= 1
            critical_alerts = [a for a in alerts if a.level == "critical"]
            assert len(critical_alerts) > 0
    
    @pytest.mark.asyncio
    async def test_predictive_alert_on_correlation(self, alert_engine, temperature_rule, humidity_rule):
        """Test predictive alert when correlated parameter is critical but base is normal."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=None)
            mock_collection.insert_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            
            alert_engine._rules_cache["prod-01:temperature"] = temperature_rule
            alert_engine._rules_cache["prod-01:humidity"] = humidity_rule
            
            # Create active critical alert for humidity
            humidity_measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="humidity",
                value=90.0,
                unit="%",
                timestamp=datetime.now(timezone.utc),
            )
            await alert_engine.check_measurement(humidity_measurement)
            
            # Now check temperature in NORMAL range - should create predictive
            temp_measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="temperature",
                value=22.0,
                unit="°C",
                timestamp=datetime.now(timezone.utc),
            )
            alerts = await alert_engine.check_measurement(temp_measurement)
            
            # Should create predictive alert
            predictive_alerts = [a for a in alerts if a.level == "predictive"]
            assert len(predictive_alerts) > 0
            assert predictive_alerts[0].metadata["correlation_trigger"] == "humidity"


class TestAlertEngineLatency:
    """Latency tests for critical path (<420ms budget)."""
    
    @pytest.fixture
    def alert_engine(self):
        engine = AlertEngine()
        engine._tracking.clear()
        engine._rules_cache.clear()
        engine._last_rules_update = None
        return engine
    
    @pytest.fixture
    def rule(self):
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
    
    @pytest.mark.asyncio
    async def test_check_measurement_latency(self, alert_engine, rule):
        """Test check_measurement completes within latency budget."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=None)
            mock_collection.insert_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            
            alert_engine._rules_cache["prod-01:temperature"] = rule
            
            measurement = MeasurementCreate(
                zone_id="prod-01",
                parameter="temperature",
                value=36.0,
                unit="°C",
                timestamp=datetime.now(timezone.utc),
            )
            
            # Measure latency
            start = datetime.now(timezone.utc)
            await alert_engine.check_measurement(measurement)
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            # Should complete well within 420ms budget
            assert elapsed < 100, f"Alert check took {elapsed:.1f}ms, budget is 420ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_checks_latency(self, alert_engine, rule):
        """Test concurrent alert checks don't exceed budget."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=None)
            mock_collection.insert_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert = AsyncMock(return_value=0)
            
            alert_engine._rules_cache["prod-01:temperature"] = rule
            
            # Create 10 concurrent measurements
            measurements = [
                MeasurementCreate(
                    zone_id="prod-01",
                    parameter="temperature",
                    value=36.0 + i * 0.1,
                    unit="°C",
                    timestamp=datetime.now(timezone.utc),
                )
                for i in range(10)
            ]
            
            start = datetime.now(timezone.utc)
            await asyncio.gather(*[alert_engine.check_measurement(m) for m in measurements])
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            # All 10 should complete within budget
            assert elapsed < 420, f"10 concurrent checks took {elapsed:.1f}ms, budget is 420ms"
    
    @pytest.mark.asyncio
    async def test_acknowledge_alert_latency(self, alert_engine):
        """Test alert acknowledgment latency."""
        with patch("app.services.alerts.get_database") as mock_db, \
             patch("app.services.alerts.get_websocket_manager") as mock_ws:
            
            mock_collection = AsyncMock()
            mock_collection.find_one_and_update = AsyncMock(return_value={
                "_id": "alert123",
                "zone_id": "prod-01",
                "parameter": "temperature",
                "level": "critical",
                "value": 36.0,
                "threshold": 35.0,
                "unit": "°C",
                "message": "CRITICAL...",
                "status": "acknowledged",
                "acknowledged_by": "user1",
                "acknowledged_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_ws.return_value.broadcast_alert_update = AsyncMock(return_value=0)
            
            start = datetime.now(timezone.utc)
            result = await alert_engine.acknowledge_alert("alert123", "user1")
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            assert result is not None
            assert elapsed < 50, f"Acknowledge took {elapsed:.1f}ms"


class TestAlertStateMachine:
    """Test alert state transitions."""
    
    def test_alert_state_enum(self):
        """Test AlertState enum values."""
        assert AlertState.NORMAL == "normal"
        assert AlertState.WARNING_PENDING == "warning_pending"
        assert AlertState.WARNING_ACTIVE == "warning_active"
        assert AlertState.CRITICAL_PENDING == "critical_pending"
        assert AlertState.CRITICAL_ACTIVE == "critical_active"
        assert AlertState.PREDICTIVE_ACTIVE == "predictive_active"
    
    def test_alert_tracking_defaults(self):
        """Test AlertTracking default values."""
        tracking = AlertTracking(zone_id="prod-01", parameter="temperature")
        
        assert tracking.zone_id == "prod-01"
        assert tracking.parameter == "temperature"
        assert tracking.state == AlertState.NORMAL
        assert tracking.warning_start is None
        assert tracking.critical_start is None
        assert tracking.last_value is None
        assert tracking.active_alert_id is None
        assert tracking.acknowledged is False
        assert tracking.correlation_triggered is False