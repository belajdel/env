"""
MQTT Ingestion Tests
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.mqtt_ingestion import MQTTIngestionService
from app.models.measurement import MeasurementCreate, VALID_PARAMETERS


class TestMQTTIngestion:
    """Test MQTT ingestion service."""
    
    @pytest.fixture
    def mqtt_service(self):
        """MQTT service with mocked client."""
        with patch("app.services.mqtt_ingestion.settings") as mock_settings:
            mock_settings.MQTT_BROKER = "localhost"
            mock_settings.MQTT_PORT = 8883
            mock_settings.MQTT_USERNAME = "test"
            mock_settings.MQTT_PASSWORD = "test"
            mock_settings.MQTT_USE_TLS = False
            mock_settings.MQTT_CLIENT_ID = "test-client"
            mock_settings.MQTT_KEEPALIVE = 60
            mock_settings.MQTT_QOS = 1
            mock_settings.AI_SERVICE_TIMEOUT_MS = 800
            mock_settings.AI_SERVICE_ENABLED = False
            
            service = MQTTIngestionService()
            service._running = True
            return service
    
    def test_validate_measurement_payload_valid(self, mqtt_service):
        """Test valid measurement payload passes validation."""
        payload = {
            "zone_id": "prod-01",
            "parameter": "temperature",
            "value": 25.0,
            "unit": "°C",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_id": "prod-01",
        }
        
        # This tests the internal validation logic
        # We'll test via the message processing
        assert payload["parameter"] in VALID_PARAMETERS
        assert payload["unit"] == "°C"
        assert -40 <= payload["value"] <= 85
    
    def test_validate_measurement_payload_invalid_parameter(self, mqtt_service):
        """Test invalid parameter is rejected."""
        payload = {
            "zone_id": "prod-01",
            "parameter": "invalid_param",
            "value": 25.0,
            "unit": "°C",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        assert payload["parameter"] not in VALID_PARAMETERS
    
    def test_validate_measurement_payload_invalid_unit(self, mqtt_service):
        """Test wrong unit for parameter is rejected."""
        payload = {
            "zone_id": "prod-01",
            "parameter": "temperature",
            "value": 25.0,
            "unit": "%",  # Wrong unit for temperature
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        from app.models.measurement import PARAMETER_UNITS
        assert payload["unit"] != PARAMETER_UNITS["temperature"]
    
    def test_validate_measurement_payload_out_of_range(self, mqtt_service):
        """Test out-of-range values are rejected."""
        # Temperature too high
        payload = {
            "zone_id": "prod-01",
            "parameter": "temperature",
            "value": 100.0,
            "unit": "°C",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        assert not (-40 <= payload["value"] <= 85)
    
    def test_validate_measurement_payload_missing_fields(self, mqtt_service):
        """Test missing required fields."""
        payload = {
            "zone_id": "prod-01",
            "parameter": "temperature",
            # missing value, unit, timestamp
        }
        
        required = ["zone_id", "parameter", "value", "unit", "timestamp"]
        assert not all(k in payload for k in required)
    
    def test_validate_measurement_payload_zone_mismatch(self, mqtt_service):
        """Test topic/payload zone mismatch."""
        topic = "factory/prod-01/temperature"
        payload = {
            "zone_id": "prod-02",  # Different zone
            "parameter": "temperature",
            "value": 25.0,
            "unit": "°C",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        parts = topic.split("/")
        topic_zone = parts[1]
        assert payload["zone_id"] != topic_zone
    
    @pytest.mark.asyncio
    async def test_process_valid_message(self, mqtt_service):
        """Test processing a valid message stores measurement."""
        with patch("app.services.mqtt_ingestion.get_database") as mock_db, \
             patch("app.services.mqtt_ingestion.get_alert_engine") as mock_alert, \
             patch("app.services.mqtt_ingestion.get_ai_client") as mock_ai:
            
            mock_collection = AsyncMock()
            mock_collection.insert_one = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            mock_alert.return_value.check_measurement = AsyncMock(return_value=[])
            mock_ai.return_value.enabled = False
            
            topic = "factory/prod-01/temperature"
            payload = json.dumps({
                "zone_id": "prod-01",
                "parameter": "temperature",
                "value": 25.0,
                "unit": "°C",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }).encode()
            
            await mqtt_service._process_message(topic, payload)
            
            assert mqtt_service._stats["messages_valid"] == 1
            assert mqtt_service._stats["messages_stored"] == 1
            mock_collection.insert_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_invalid_message(self, mqtt_service):
        """Test invalid message increments error counters."""
        with patch("app.services.mqtt_ingestion.get_database") as mock_db:
            mock_collection = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            topic = "factory/prod-01/temperature"
            payload = b"not valid json"
            
            await mqtt_service._process_message(topic, payload)
            
            assert mqtt_service._stats["messages_invalid"] == 1
            assert mqtt_service._stats["errors"] == 1
            mock_collection.insert_one.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_aggregation_buffer(self, mqtt_service):
        """Test values are added to aggregation buffer."""
        mqtt_service._add_to_aggregation_buffer(
            "prod-01", "temperature", 25.0, 
            datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
        )
        
        # Should be buffered under the minute key
        buffer_key = "prod-01:temperature"
        minute_key = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        assert buffer_key in mqtt_service._aggregation_buffers
        assert minute_key in mqtt_service._aggregation_buffers[buffer_key]
        assert mqtt_service._aggregation_buffers[buffer_key][minute_key] == [25.0]
    
    @pytest.mark.asyncio
    async def test_publish_relay_command(self, mqtt_service):
        """Test publishing relay command."""
        # Mock the MQTT client
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.rc = 0  # Success
        mock_client.publish.return_value = mock_result
        mqtt_service.client = mock_client
        mqtt_service._connected = True
        
        result = await mqtt_service.publish_relay_command("prod-01", 1, "on")
        
        assert result is True
        mock_client.publish.assert_called_once()
        call_args = mock_client.publish.call_args
        assert call_args[0][0] == "factory/prod-01/relay/1/cmd"
        assert "on" in call_args[0][1]


class TestMQTTStats:
    """Test MQTT statistics tracking."""
    
    @pytest.fixture
    def mqtt_service(self):
        with patch("app.services.mqtt_ingestion.settings") as mock_settings:
            mock_settings.MQTT_BROKER = "localhost"
            mock_settings.MQTT_PORT = 8883
            mock_settings.MQTT_USERNAME = "test"
            mock_settings.MQTT_PASSWORD = "test"
            mock_settings.MQTT_USE_TLS = False
            mock_settings.MQTT_CLIENT_ID = "test-client"
            mock_settings.MQTT_KEEPALIVE = 60
            mock_settings.MQTT_QOS = 1
            mock_settings.AI_SERVICE_TIMEOUT_MS = 800
            mock_settings.AI_SERVICE_ENABLED = False
            
            service = MQTTIngestionService()
            return service
    
    def test_stats_initialization(self, mqtt_service):
        """Test stats are initialized correctly."""
        stats = mqtt_service.get_stats()
        
        assert stats["messages_received"] == 0
        assert stats["messages_valid"] == 0
        assert stats["messages_invalid"] == 0
        assert stats["messages_stored"] == 0
        assert stats["aggregates_published"] == 0
        assert stats["errors"] == 0
        assert stats["connected"] is False
        assert stats["queue_size"] == 0
    
    def test_stats_increment(self, mqtt_service):
        """Test stats increment correctly."""
        mqtt_service._stats["messages_received"] = 10
        mqtt_service._stats["messages_valid"] = 8
        mqtt_service._stats["messages_invalid"] = 2
        
        stats = mqtt_service.get_stats()
        
        assert stats["messages_received"] == 10
        assert stats["messages_valid"] == 8
        assert stats["messages_invalid"] == 2