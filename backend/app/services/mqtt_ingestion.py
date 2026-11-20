"""
MQTT Ingestion Service
Subscribes to sensor topics, validates payloads, stores measurements, publishes aggregates.
"""

import asyncio
import json
import time
import ssl
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Set, Callable, Awaitable
from collections import defaultdict

import paho.mqtt.client as mqtt
from pymongo import ASCENDING

from app.core.config import settings
from app.core.database import get_database, Collections
from app.core.logging import get_logger
from app.models.measurement import MeasurementCreate, VALID_PARAMETERS, PARAMETER_UNITS
from app.services.alerts import get_alert_engine
from app.services.ai_client import get_ai_client

logger = get_logger(__name__)


class MQTTIngestionService:
    """MQTT subscriber for sensor data ingestion."""
    
    def __init__(self):
        self.client: Optional[mqtt.Client] = None
        self._connected = False
        self._subscribed_topics: Set[str] = set()
        self._running = False
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._worker_tasks: list[asyncio.Task] = []
        self._aggregation_task: Optional[asyncio.Task] = None
        self._stats = {
            "messages_received": 0,
            "messages_valid": 0,
            "messages_invalid": 0,
            "messages_stored": 0,
            "aggregates_published": 0,
            "errors": 0,
            "last_message_time": None,
        }
        self._aggregation_buffers: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self._last_aggregate_minute: Optional[int] = None
    
    async def start(self) -> None:
        """Start MQTT client and worker tasks."""
        if self._running:
            return
        
        self._running = True
        logger.info("starting_mqtt_ingestion")
        
        # Create MQTT client
        self.client = mqtt.Client(
            client_id=settings.MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        
        self.client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        
        if settings.MQTT_USE_TLS:
            try:
                self.client.tls_set(
                    ca_certs=settings.MQTT_CA_CERT,
                    certfile=None,
                    keyfile=None,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS,
                    ciphers=None,
                )
                self.client.tls_insecure_set(False)
            except Exception as e:
                logger.error("mqtt_tls_setup_failed", error=str(e))
                raise
        
        # Callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe
        
        # Connect
        try:
            self.client.connect_async(settings.MQTT_BROKER, settings.MQTT_PORT, keepalive=settings.MQTT_KEEPALIVE)
            self.client.loop_start()
            
            # Wait for connection
            for _ in range(50):  # 5 seconds
                if self._connected:
                    break
                await asyncio.sleep(0.1)
            else:
                raise TimeoutError("MQTT connection timeout")
        except Exception as e:
            logger.error("mqtt_connect_failed", error=str(e))
            self._running = False
            raise
        
        # Start worker tasks
        num_workers = 4
        for i in range(num_workers):
            task = asyncio.create_task(self._message_worker(i))
            self._worker_tasks.append(task)
        
        # Start aggregation task
        self._aggregation_task = asyncio.create_task(self._aggregation_worker())
        
        logger.info("mqtt_ingestion_started", workers=num_workers)
    
    async def stop(self) -> None:
        """Stop MQTT client and worker tasks."""
        if not self._running:
            return
        
        self._running = False
        logger.info("stopping_mqtt_ingestion")
        
        # Cancel workers
        for task in self._worker_tasks:
            task.cancel()
        for task in self._worker_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        if self._aggregation_task:
            self._aggregation_task.cancel()
            try:
                await self._aggregation_task
            except asyncio.CancelledError:
                pass
        
        # Flush any pending aggregates
        await self._flush_aggregates()
        
        # Disconnect MQTT
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        
        logger.info("mqtt_ingestion_stopped", stats=self._stats)
    
    def _on_connect(self, client, userdata, flags, rc) -> None:
        """MQTT connect callback."""
        if rc == 0:
            self._connected = True
            logger.info("mqtt_connected")
            
            # Subscribe to all zone measurement topics
            zones = ["prod-01", "prod-02", "prod-03", "store-01", "store-02", "tech-01", "tech-02"]
            for zone in zones:
                for param in VALID_PARAMETERS:
                    topic = f"factory/{zone}/{param}"
                    client.subscribe(topic, qos=settings.MQTT_QOS)
                    self._subscribed_topics.add(topic)
            
            # Subscribe to device status topics
            for zone in zones:
                topic = f"factory/{zone}/status"
                client.subscribe(topic, qos=settings.MQTT_QOS)
                self._subscribed_topics.add(topic)
            
            logger.info("mqtt_subscribed", topics=len(self._subscribed_topics))
        else:
            logger.error("mqtt_connect_failed", rc=rc)
    
    def _on_disconnect(self, client, userdata, rc) -> None:
        """MQTT disconnect callback."""
        self._connected = False
        if rc != 0:
            logger.warning("mqtt_unexpected_disconnect", rc=rc)
        else:
            logger.info("mqtt_disconnected")
    
    def _on_message(self, client, userdata, msg) -> None:
        """MQTT message callback - puts message in queue for async processing."""
        self._stats["messages_received"] += 1
        self._stats["last_message_time"] = datetime.now(timezone.utc).isoformat()
        
        try:
            self._message_queue.put_nowait((msg.topic, msg.payload, msg.qos, msg.retain))
        except asyncio.QueueFull:
            self._stats["errors"] += 1
            logger.warning("mqtt_queue_full_dropping_message", topic=msg.topic)
    
    def _on_subscribe(self, client, userdata, mid, granted_qos) -> None:
        """MQTT subscribe callback."""
        logger.debug("mqtt_subscribe_confirmed", mid=mid, qos=granted_qos)
    
    async def _message_worker(self, worker_id: int) -> None:
        """Process messages from queue."""
        logger.debug("mqtt_worker_started", worker_id=worker_id)
        
        while self._running:
            try:
                topic, payload, qos, retain = await asyncio.wait_for(
                    self._message_queue.get(), timeout=1.0
                )
                await self._process_message(topic, payload)
                self._message_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._stats["errors"] += 1
                logger.error("mqtt_worker_error", worker_id=worker_id, error=str(e))
        
        logger.debug("mqtt_worker_stopped", worker_id=worker_id)
    
    async def _process_message(self, topic: str, payload: bytes) -> None:
        """Process a single MQTT message."""
        try:
            # Parse topic: factory/{zone_id}/{parameter}
            parts = topic.split("/")
            if len(parts) != 3 or parts[0] != "factory":
                logger.debug("mqtt_invalid_topic_format", topic=topic)
                self._stats["messages_invalid"] += 1
                return
            
            _, zone_id, parameter = parts
            
            # Validate zone
            valid_zones = ["prod-01", "prod-02", "prod-03", "store-01", "store-02", "tech-01", "tech-02"]
            if zone_id not in valid_zones:
                logger.debug("mqtt_invalid_zone", zone_id=zone_id)
                self._stats["messages_invalid"] += 1
                return
            
            # Validate parameter
            if parameter not in VALID_PARAMETERS:
                logger.debug("mqtt_invalid_parameter", parameter=parameter)
                self._stats["messages_invalid"] += 1
                return
            
            # Parse payload
            try:
                data = json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:
                logger.warning("mqtt_invalid_json", topic=topic)
                self._stats["messages_invalid"] += 1
                return
            
            # Validate required fields
            required = ["zone_id", "parameter", "value", "unit", "timestamp"]
            if not all(k in data for k in required):
                logger.warning("mqtt_missing_fields", topic=topic, data=data)
                self._stats["messages_invalid"] += 1
                return
            
            # Cross-validate
            if data["zone_id"] != zone_id or data["parameter"] != parameter:
                logger.warning("mqtt_topic_payload_mismatch", topic=topic, data=data)
                self._stats["messages_invalid"] += 1
                return
            
            # Validate unit
            expected_unit = PARAMETER_UNITS[parameter]
            if data["unit"] != expected_unit:
                logger.warning("mqtt_invalid_unit", topic=topic, expected=expected_unit, got=data["unit"])
                self._stats["messages_invalid"] += 1
                return
            
            # Validate value ranges
            value = float(data["value"])
            ranges = {
                "temperature": (-40, 85),
                "humidity": (0, 100),
                "noise": (30, 130),
                "air_quality": (0, 10000),
                "pm25": (0, 500),
                "pm10": (0, 1000),
                "voltage": (0, 300),
            }
            min_v, max_v = ranges[parameter]
            if not (min_v <= value <= max_v):
                logger.warning("mqtt_value_out_of_range", topic=topic, value=value, range=(min_v, max_v))
                self._stats["messages_invalid"] += 1
                return
            
            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            except Exception:
                logger.warning("mqtt_invalid_timestamp", topic=topic, timestamp=data["timestamp"])
                self._stats["messages_invalid"] += 1
                return
            
            # Check timestamp not too old/future
            now = datetime.now(timezone.utc)
            if timestamp < now - timedelta(hours=1) or timestamp > now + timedelta(minutes=5):
                logger.warning("mqtt_timestamp_suspicious", topic=topic, timestamp=timestamp.isoformat())
            
            # Create measurement object
            measurement = MeasurementCreate(
                zone_id=zone_id,
                parameter=parameter,
                value=value,
                unit=data["unit"],
                device_id=data.get("device_id"),
                timestamp=timestamp,
                metadata=data.get("metadata"),
            )
            
            # Store in database
            await self._store_measurement(measurement)
            
            # Add to aggregation buffer
            self._add_to_aggregation_buffer(zone_id, parameter, value, timestamp)
            
            # Check alerts
            alert_engine = get_alert_engine()
            await alert_engine.check_measurement(measurement)
            
            # Call AI service for prediction (async, non-blocking)
            ai_client = get_ai_client()
            if ai_client.enabled:
                asyncio.create_task(self._call_ai_prediction(measurement))
            
            self._stats["messages_valid"] += 1
            self._stats["messages_stored"] += 1
            
        except Exception as e:
            self._stats["messages_invalid"] += 1
            self._stats["errors"] += 1
            logger.error("mqtt_process_error", topic=topic, error=str(e))
    
    async def _store_measurement(self, measurement: MeasurementCreate) -> None:
        """Store measurement in time-series collection."""
        db = get_database()
        
        doc = measurement.model_dump()
        doc["metadata"] = doc.get("metadata") or {}
        doc["metadata"]["ingested_at"] = datetime.now(timezone.utc)
        
        await db[Collections.MEASUREMENTS].insert_one(doc)
    
    def _add_to_aggregation_buffer(
        self, zone_id: str, parameter: str, value: float, timestamp: datetime
    ) -> None:
        """Add value to aggregation buffer for 1-minute aggregates."""
        # Round timestamp to minute
        minute_key = timestamp.replace(second=0, microsecond=0)
        buffer_key = f"{zone_id}:{parameter}"
        
        self._aggregation_buffers[buffer_key][minute_key].append(value)
    
    async def _aggregation_worker(self) -> None:
        """Compute and publish 1-minute aggregates every minute."""
        logger.debug("mqtt_aggregation_worker_started")
        
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                current_minute = now.replace(second=0, microsecond=0)
                
                # Process previous minute's data
                if self._last_aggregate_minute is not None:
                    prev_minute = self._last_aggregate_minute
                    await self._compute_and_store_aggregates(prev_minute)
                
                self._last_aggregate_minute = current_minute
                
                # Sleep until next minute
                next_minute = current_minute + timedelta(minutes=1)
                sleep_seconds = (next_minute - now).total_seconds()
                await asyncio.sleep(max(1, sleep_seconds))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("mqtt_aggregation_error", error=str(e))
                await asyncio.sleep(10)
        
        logger.debug("mqtt_aggregation_worker_stopped")
    
    async def _compute_and_store_aggregates(self, minute: datetime) -> None:
        """Compute aggregates for a specific minute."""
        db = get_database()
        
        for buffer_key, minute_data in list(self._aggregation_buffers.items()):
            if minute in minute_data:
                values = minute_data.pop(minute)
                if not values:
                    continue
                
                zone_id, parameter = buffer_key.split(":", 1)
                
                # Compute statistics
                count = len(values)
                min_v = min(values)
                max_v = max(values)
                avg_v = sum(values) / count
                
                # Standard deviation
                if count > 1:
                    variance = sum((v - avg_v) ** 2 for v in values) / count
                    std_v = variance ** 0.5
                else:
                    std_v = 0.0
                
                # Store aggregate
                aggregate_doc = {
                    "metadata": {
                        "zone_id": zone_id,
                        "parameter": parameter,
                        "device_id": None,
                    },
                    "timestamp": minute,
                    "count": count,
                    "min": min_v,
                    "max": max_v,
                    "avg": avg_v,
                    "std": std_v,
                    "unit": PARAMETER_UNITS[parameter],
                }
                
                await db[Collections.MEASUREMENTS_1MIN].insert_one(aggregate_doc)
                self._stats["aggregates_published"] += 1
        
        # Cleanup old buffers (keep last 5 minutes)
        cutoff = minute - timedelta(minutes=5)
        for buffer_key in list(self._aggregation_buffers.keys()):
            minute_data = self._aggregation_buffers[buffer_key]
            keys_to_remove = [k for k in minute_data if k < cutoff]
            for k in keys_to_remove:
                del minute_data[k]
            if not minute_data:
                del self._aggregation_buffers[buffer_key]
    
    async def _flush_aggregates(self) -> None:
        """Flush any remaining aggregation buffers."""
        if self._last_aggregate_minute:
            await self._compute_and_store_aggregates(self._last_aggregate_minute)
    
    async def _call_ai_prediction(self, measurement: MeasurementCreate) -> None:
        """Call AI service for prediction (fire and forget with timeout)."""
        ai_client = get_ai_client()
        try:
            await asyncio.wait_for(
                ai_client.predict_single(measurement.zone_id, measurement.parameter, measurement.value),
                timeout=settings.AI_SERVICE_TIMEOUT_MS / 1000,
            )
        except asyncio.TimeoutError:
            logger.debug("ai_prediction_timeout", zone=measurement.zone_id, param=measurement.parameter)
        except Exception as e:
            logger.debug("ai_prediction_error", zone=measurement.zone_id, error=str(e))
    
    def get_stats(self) -> Dict:
        """Get ingestion statistics."""
        return {
            **self._stats,
            "connected": self._connected,
            "queue_size": self._message_queue.qsize(),
            "buffered_minutes": sum(len(d) for d in self._aggregation_buffers.values()),
        }
    
    async def publish_relay_command(self, zone_id: str, relay_id: int, command: str) -> bool:
        """Publish relay command to MQTT."""
        if not self.client or not self._connected:
            return False
        
        topic = f"factory/{zone_id}/relay/{relay_id}/cmd"
        payload = json.dumps({"command": command, "timestamp": datetime.now(timezone.utc).isoformat()})
        
        result = self.client.publish(topic, payload, qos=1)
        return result.rc == 0


_mqtt_service: Optional[MQTTIngestionService] = None


def get_mqtt_service() -> MQTTIngestionService:
    """Get singleton MQTTIngestionService instance."""
    global _mqtt_service
    if _mqtt_service is None:
        _mqtt_service = MQTTIngestionService()
    return _mqtt_service