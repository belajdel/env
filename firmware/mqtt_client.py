"""
MQTT Client with TLS, Exponential Backoff, LWT, Retained Status, Offline Ring Buffer
MicroPython compatible (uses umqtt.simple or umqtt.robust)
"""

import time
import json
import ssl
import machine
import gc
from collections import deque
from typing import Optional, Callable, Dict, Any, List
from ..config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID,
    MQTT_KEEPALIVE, MQTT_USE_TLS, CA_CERT_PATH, CLIENT_CERT_PATH, CLIENT_KEY_PATH,
    TOPIC_STATUS, TOPIC_STATE, LWT_TOPIC, LWT_PAYLOAD, LWT_QOS, LWT_RETAIN,
    STATUS_RETAIN, STATE_RETAIN, TOPIC_BASE, VALID_PARAMETERS,
    RECONNECT_BASE_DELAY_MS, RECONNECT_MAX_DELAY_MS, RECONNECT_JITTER_MS,
    MAX_OFFLINE_BUFFER_SIZE, SAMPLING_INTERVAL_MS
)


class OfflineBuffer:
    """Ring buffer for storing messages when offline."""
    
    def __init__(self, max_size: int = MAX_OFFLINE_BUFFER_SIZE):
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        self._overflow_count = 0
        
    def add(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> bool:
        """Add message to buffer. Returns True if added, False if buffer full (overflow)."""
        if len(self.buffer) >= self.max_size:
            self._overflow_count += 1
            # Remove oldest non-retained message to make space
            for i, msg in enumerate(self.buffer):
                if not msg.get('retain', False):
                    self.buffer.remove(msg)
                    break
            else:
                # All messages are retained, remove oldest
                self.buffer.popleft()
                
        self.buffer.append({
            'topic': topic,
            'payload': payload,
            'qos': qos,
            'retain': retain,
            'timestamp': time.time()
        })
        return True
        
    def get_all(self) -> List[Dict]:
        """Get all buffered messages and clear buffer."""
        messages = list(self.buffer)
        self.buffer.clear()
        return messages
        
    def size(self) -> int:
        """Get current buffer size."""
        return len(self.buffer)
        
    def overflow_count(self) -> int:
        """Get number of overflow events."""
        return self._overflow_count
        
    def clear(self) -> None:
        """Clear buffer."""
        self.buffer.clear()
        self._overflow_count = 0


class MQTTClient:
    """MQTT client with TLS, reconnection, LWT, and offline buffering."""
    
    def __init__(self, client_id: str = None, 
                 broker: str = MQTT_BROKER, port: int = MQTT_PORT,
                 username: str = MQTT_USERNAME, password: str = MQTT_PASSWORD,
                 keepalive: int = MQTT_KEEPALIVE, use_tls: bool = MQTT_USE_TLS):
        self.client_id = client_id or MQTT_CLIENT_ID
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.keepalive = keepalive
        self.use_tls = use_tls
        
        # Connection state
        self._client = None
        self._connected = False
        self._connecting = False
        self._last_connect_attempt = 0
        self._reconnect_delay = RECONNECT_BASE_DELAY_MS
        self._message_callback = None
        self._connection_callback = None
        self._disconnection_callback = None
        
        # Offline buffer
        self.offline_buffer = OfflineBuffer()
        
        # Status tracking
        self._last_ping = 0
        self._ping_interval = 30000  # 30 seconds
        self._incoming_messages = 0
        self._outgoing_messages = 0
        self._errors = 0
        
        # Subscription tracking
        self._subscriptions = set()
        self._pending_subscriptions = set()
        
    def set_callbacks(self, 
                      message_callback: Callable[[str, bytes], None] = None,
                      connection_callback: Callable[[], None] = None,
                      disconnection_callback: Callable[[], None] = None) -> None:
        """Set callback functions."""
        self._message_callback = message_callback
        self._connection_callback = connection_callback
        self._disconnection_callback = disconnection_callback
        
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for TLS connection."""
        if not self.use_tls:
            return None
            
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(CA_CERT_PATH)
            context.load_cert_chain(CLIENT_CERT_PATH, CLIENT_KEY_PATH)
            return context
        except Exception as e:
            print(f"SSL context creation failed: {e}")
            return None
            
    def connect(self) -> bool:
        """Connect to MQTT broker."""
        if self._connected or self._connecting:
            return self._connected
            
        self._connecting = True
        print(f"Connecting to MQTT broker {self.broker}:{self.port}...")
        
        try:
            # Import here to avoid issues if not available
            from umqtt.simple import MQTTClient as UMQTTClient
            
            ssl_context = self._create_ssl_context() if self.use_tls else None
            
            self._client = UMQTTClient(
                client_id=self.client_id,
                server=self.broker,
                port=self.port,
                user=self.username,
                password=self.password,
                keepalive=self.keepalive,
                ssl=ssl_context
            )
            
            # Set LWT
            self._client.set_last_will(LWT_TOPIC, LWT_PAYLOAD, retain=LWT_RETAIN, qos=LWT_QOS)
            
            # Set callback
            self._client.set_callback(self._on_message)
            
            # Connect
            self._client.connect()
            
            # Subscribe to pending topics
            for topic in self._pending_subscriptions:
                self._client.subscribe(topic)
                self._subscriptions.add(topic)
            self._pending_subscriptions.clear()
            
            # Publish online status
            self._publish_status("online", "connected")
            
            self._connected = True
            self._connecting = False
            self._reconnect_delay = RECONNECT_BASE_DELAY_MS
            self._last_connect_attempt = time.ticks_ms()
            self._last_ping = time.ticks_ms()
            
            # Flush offline buffer
            self._flush_offline_buffer()
            
            if self._connection_callback:
                self._connection_callback()
                
            print("MQTT connected successfully")
            gc.collect()
            return True
            
        except Exception as e:
            self._connecting = False
            self._connected = False
            self._errors += 1
            print(f"MQTT connection failed: {e}")
            self._schedule_reconnect()
            return False
            
    def _on_message(self, topic: bytes, msg: bytes) -> None:
        """Internal message handler."""
        self._incoming_messages += 1
        topic_str = topic.decode('utf-8')
        if self._message_callback:
            try:
                self._message_callback(topic_str, msg)
            except Exception as e:
                print(f"Message callback error: {e}")
                
    def _publish_status(self, status: str, reason: str = "") -> None:
        """Publish device status (retained)."""
        payload = json.dumps({
            "status": status,
            "reason": reason,
            "timestamp": time.time(),
            "device_id": self.client_id,
            "firmware_version": "1.0.0"
        })
        self.publish(TOPIC_STATUS, payload, qos=1, retain=STATUS_RETAIN)
        
    def _publish_state(self, state: dict) -> None:
        """Publish device state (retained)."""
        payload = json.dumps({
            **state,
            "timestamp": time.time(),
            "device_id": self.client_id
        })
        self.publish(TOPIC_STATE, payload, qos=1, retain=STATE_RETAIN)
        
    def publish(self, topic: str, payload: str, qos: int = 1, retain: bool = False) -> bool:
        """Publish message, buffering if offline."""
        if self._connected and self._client:
            try:
                self._client.publish(topic, payload, qos=qos, retain=retain)
                self._outgoing_messages += 1
                return True
            except Exception as e:
                print(f"Publish failed: {e}")
                self._errors += 1
                self._handle_disconnect()
                # Buffer for later
                return self.offline_buffer.add(topic, payload, qos, retain)
        else:
            # Buffer for when we reconnect
            return self.offline_buffer.add(topic, payload, qos, retain)
            
    def publish_measurement(self, parameter: str, value: float, unit: str) -> bool:
        """Publish a sensor measurement."""
        if parameter not in VALID_PARAMETERS:
            return False
            
        topic = f"{TOPIC_BASE}/{parameter}"
        payload = json.dumps({
            "zone_id": TOPIC_BASE.split('/')[-1],
            "parameter": parameter,
            "value": value,
            "unit": unit,
            "timestamp": time.time()
        })
        return self.publish(topic, payload, qos=1, retain=False)
        
    def subscribe(self, topic: str) -> bool:
        """Subscribe to topic."""
        if self._connected and self._client:
            try:
                self._client.subscribe(topic)
                self._subscriptions.add(topic)
                return True
            except Exception as e:
                print(f"Subscribe failed: {e}")
                self._errors += 1
                self._pending_subscriptions.add(topic)
                return False
        else:
            self._pending_subscriptions.add(topic)
            return True
            
    def unsubscribe(self, topic: str) -> bool:
        """Unsubscribe from topic."""
        if self._connected and self._client:
            try:
                self._client.unsubscribe(topic)
                self._subscriptions.discard(topic)
                self._pending_subscriptions.discard(topic)
                return True
            except Exception as e:
                print(f"Unsubscribe failed: {e}")
                return False
        else:
            self._pending_subscriptions.discard(topic)
            return True
            
    def _flush_offline_buffer(self) -> None:
        """Flush all buffered messages after reconnection."""
        messages = self.offline_buffer.get_all()
        if messages:
            print(f"Flushing {len(messages)} buffered messages...")
            for msg in messages:
                try:
                    self._client.publish(
                        msg['topic'], msg['payload'], 
                        qos=msg['qos'], retain=msg['retain']
                    )
                    self._outgoing_messages += 1
                except Exception as e:
                    print(f"Failed to flush message: {e}")
                    # Re-buffer
                    self.offline_buffer.add(
                        msg['topic'], msg['payload'], msg['qos'], msg['retain']
                    )
                    
    def _handle_disconnect(self) -> None:
        """Handle disconnection."""
        if self._connected:
            self._connected = False
            print("MQTT disconnected")
            if self._disconnection_callback:
                self._disconnection_callback()
            self._schedule_reconnect()
            
    def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff."""
        self._reconnect_delay = min(
            self._reconnect_delay * 2, 
            RECONNECT_MAX_DELAY_MS
        )
        # Add jitter
        import random
        self._reconnect_delay += random.randint(0, RECONNECT_JITTER_MS)
        
    def reconnect(self) -> bool:
        """Attempt reconnection."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_connect_attempt) < self._reconnect_delay:
            return False
            
        self._last_connect_attempt = now
        return self.connect()
        
    def check_connection(self) -> bool:
        """Check connection and attempt reconnect if needed."""
        if not self._connected:
            return self.reconnect()
            
        # Check if we need to ping
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_ping) >= self._ping_interval:
            try:
                self._client.ping()
                self._last_ping = now
            except Exception as e:
                print(f"Ping failed: {e}")
                self._handle_disconnect()
                return False
                
        return True
        
    def loop(self, timeout_ms: int = 100) -> None:
        """Process incoming messages (call regularly)."""
        if self._connected and self._client:
            try:
                self._client.check_msg()
            except Exception as e:
                print(f"MQTT loop error: {e}")
                self._handle_disconnect()
                
    def wait_msg(self, timeout_ms: int = 1000) -> None:
        """Wait for incoming message (blocking)."""
        if self._connected and self._client:
            try:
                self._client.wait_msg()
            except Exception as e:
                print(f"Wait msg error: {e}")
                self._handle_disconnect()
                
    def disconnect(self) -> None:
        """Graceful disconnect."""
        if self._connected:
            self._publish_status("offline", "graceful_disconnect")
            time.sleep_ms(100)  # Allow message to send
            try:
                self._client.disconnect()
            except:
                pass
            self._connected = False
            print("MQTT disconnected gracefully")
            
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected
        
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "connected": self._connected,
            "connecting": self._connecting,
            "broker": self.broker,
            "port": self.port,
            "client_id": self.client_id,
            "incoming_messages": self._incoming_messages,
            "outgoing_messages": self._outgoing_messages,
            "errors": self._errors,
            "offline_buffer_size": self.offline_buffer.size(),
            "overflow_count": self.offline_buffer.overflow_count(),
            "subscriptions": list(self._subscriptions),
            "reconnect_delay_ms": self._reconnect_delay,
        }
        
    def get_status_payload(self) -> str:
        """Get current status payload."""
        return json.dumps({
            "status": "online" if self._connected else "offline",
            "timestamp": time.time(),
            "device_id": self.client_id,
            "stats": self.get_stats()
        })