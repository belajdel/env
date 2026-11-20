"""
MQTT Publisher for Simulator
Handles TLS connections, per-device credentials, and publishing.
"""

import json
import time
import ssl
import threading
from typing import Dict, Optional, Callable, Any
from .config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USE_TLS, DEVICE_CREDENTIALS,
    CA_CERT_PATH, CLIENT_CERTS_DIR, ZONES, VALID_PARAMETERS,
    TOPIC_TEMPLATE, TOPIC_STATUS_TEMPLATE, TOPIC_STATE_TEMPLATE,
    PUBLISH_QOS, PUBLISH_RETAIN, STATUS_RETAIN, STATE_RETAIN,
    PARAMETER_UNITS
)


class SimulatorMQTTClient:
    """MQTT client for a single simulated device."""
    
    def __init__(self, zone_id: str):
        self.zone_id = zone_id
        self.credentials = DEVICE_CREDENTIALS.get(zone_id, {})
        self.username = self.credentials.get('username', zone_id)
        self.password = self.credentials.get('password', '')
        self.client_id = f"{zone_id}-sim-{int(time.time())}"
        
        self._client = None
        self._connected = False
        self._lock = threading.Lock()
        self._message_callback = None
        self._subscriptions = set()
        
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for TLS."""
        if not MQTT_USE_TLS:
            return None
            
        try:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.load_verify_locations(CA_CERT_PATH)
            
            # Load client cert if available
            cert_path = f"{CLIENT_CERTS_DIR}/{self.zone_id}.crt"
            key_path = f"{CLIENT_CERTS_DIR}/{self.zone_id}.key"
            try:
                context.load_cert_chain(cert_path, key_path)
            except FileNotFoundError:
                print(f"Warning: Client cert not found for {self.zone_id}, using username/password only")
                
            return context
        except Exception as e:
            print(f"SSL context creation failed for {self.zone_id}: {e}")
            return None
    
    def connect(self) -> bool:
        """Connect to MQTT broker."""
        with self._lock:
            if self._connected:
                return True
                
            try:
                import paho.mqtt.client as mqtt
                
                self._client = mqtt.Client(
                    client_id=self.client_id,
                    protocol=mqtt.MQTTv311,
                    clean_session=True
                )
                
                self._client.username_pw_set(self.username, self.password)
                
                if MQTT_USE_TLS:
                    ssl_context = self._create_ssl_context()
                    if ssl_context:
                        self._client.tls_set_context(ssl_context)
                    else:
                        self._client.tls_set(CA_CERT_PATH)
                        self._client.tls_insecure_set(False)
                
                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                self._client.on_message = self._on_message
                self._client.on_publish = self._on_publish
                
                self._client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
                self._client.loop_start()
                
                # Wait for connection
                timeout = 10
                while not self._connected and timeout > 0:
                    time.sleep(0.1)
                    timeout -= 0.1
                    
                return self._connected
                
            except Exception as e:
                print(f"MQTT connect failed for {self.zone_id}: {e}")
                return False
    
    def _on_connect(self, client, userdata, flags, rc) -> None:
        """Connection callback."""
        if rc == 0:
            self._connected = True
            print(f"[{self.zone_id}] MQTT connected")
            
            # Subscribe to relay commands
            relay_topic = f"factory/{self.zone_id}/relay/+/cmd"
            client.subscribe(relay_topic, qos=1)
            self._subscriptions.add(relay_topic)
            
            # Publish online status
            self.publish_status("online", "simulator_started")
        else:
            print(f"[{self.zone_id}] MQTT connection failed: {rc}")
            self._connected = False
    
    def _on_disconnect(self, client, userdata, rc) -> None:
        """Disconnection callback."""
        self._connected = False
        if rc != 0:
            print(f"[{self.zone_id}] MQTT unexpected disconnect: {rc}")
        else:
            print(f"[{self.zone_id}] MQTT disconnected")
    
    def _on_message(self, client, userdata, msg) -> None:
        """Message callback."""
        if self._message_callback:
            self._message_callback(msg.topic, msg.payload)
    
    def _on_publish(self, client, userdata, mid) -> None:
        """Publish callback."""
        pass
    
    def publish(self, topic: str, payload: str, qos: int = PUBLISH_QOS, retain: bool = PUBLISH_RETAIN) -> bool:
        """Publish message."""
        with self._lock:
            if not self._connected or not self._client:
                return False
            try:
                result = self._client.publish(topic, payload, qos=qos, retain=retain)
                return result.rc == 0
            except Exception as e:
                print(f"[{self.zone_id}] Publish failed: {e}")
                return False
    
    def publish_measurement(self, parameter: str, value: float, timestamp: float = None) -> bool:
        """Publish a sensor measurement."""
        if parameter not in VALID_PARAMETERS:
            return False
            
        topic = TOPIC_TEMPLATE.format(zone_id=self.zone_id, parameter=parameter)
        if timestamp is None:
            timestamp = time.time()
            
        payload = json.dumps({
            "zone_id": self.zone_id,
            "parameter": parameter,
            "value": value,
            "unit": PARAMETER_UNITS[parameter],
            "timestamp": timestamp
        })
        return self.publish(topic, payload, qos=1, retain=False)
    
    def publish_status(self, status: str, reason: str = "") -> bool:
        """Publish device status (retained)."""
        topic = TOPIC_STATUS_TEMPLATE.format(zone_id=self.zone_id)
        payload = json.dumps({
            "status": status,
            "reason": reason,
            "timestamp": time.time(),
            "device_id": self.zone_id,
            "simulator": True
        })
        return self.publish(topic, payload, qos=1, retain=STATUS_RETAIN)
    
    def publish_state(self, state: Dict) -> bool:
        """Publish device state (retained)."""
        topic = TOPIC_STATE_TEMPLATE.format(zone_id=self.zone_id)
        payload = json.dumps({
            **state,
            "timestamp": time.time(),
            "device_id": self.zone_id,
            "simulator": True
        })
        return self.publish(topic, payload, qos=1, retain=STATE_RETAIN)
    
    def set_message_callback(self, callback: Callable[[str, bytes], None]) -> None:
        """Set message callback."""
        self._message_callback = callback
    
    def disconnect(self) -> None:
        """Disconnect gracefully."""
        with self._lock:
            if self._connected:
                self.publish_status("offline", "simulator_stopped")
                time.sleep(0.1)
            if self._client:
                self._client.loop_stop()
                self._client.disconnect()
            self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected


class MultiZoneMQTTPublisher:
    """Manages MQTT clients for all simulated zones."""
    
    def __init__(self):
        self.clients = {}
        self._running = False
        self._publish_thread = None
        self._sensor_model = None
        self._publish_interval = 10  # seconds
        
    def initialize(self, sensor_model) -> None:
        """Initialize with sensor model."""
        self._sensor_model = sensor_model
        for zone_id in ZONES:
            self.clients[zone_id] = SimulatorMQTTClient(zone_id)
    
    def connect_all(self) -> Dict[str, bool]:
        """Connect all clients."""
        results = {}
        for zone_id, client in self.clients.items():
            results[zone_id] = client.connect()
            if results[zone_id]:
                # Set up relay command handler
                client.set_message_callback(self._handle_relay_command)
        return results
    
    def _handle_relay_command(self, topic: str, payload: bytes) -> None:
        """Handle incoming relay commands (simulator just logs)."""
        try:
            data = json.loads(payload.decode('utf-8'))
            command = data.get('command', '')
            print(f"[SIM] Relay command received: {topic} -> {command}")
        except Exception as e:
            print(f"[SIM] Relay command parse error: {e}")
    
    def publish_all_measurements(self, readings: Dict[str, Dict[str, Optional[float]]], 
                                  timestamp: float = None) -> Dict[str, Dict[str, bool]]:
        """Publish measurements for all zones."""
        if timestamp is None:
            timestamp = time.time()
            
        results = {}
        for zone_id, zone_readings in readings.items():
            client = self.clients.get(zone_id)
            if not client or not client.is_connected():
                results[zone_id] = {p: False for p in zone_readings}
                continue
                
            zone_results = {}
            for param, value in zone_readings.items():
                if value is not None:
                    zone_results[param] = client.publish_measurement(param, value, timestamp)
                else:
                    zone_results[param] = False  # Dropout
            results[zone_id] = zone_results
            
        return results
    
    def publish_all_status(self, status: str, reason: str = "") -> Dict[str, bool]:
        """Publish status for all zones."""
        results = {}
        for zone_id, client in self.clients.items():
            if client.is_connected():
                results[zone_id] = client.publish_status(status, reason)
            else:
                results[zone_id] = False
        return results
    
    def disconnect_all(self) -> None:
        """Disconnect all clients."""
        for client in self.clients.values():
            client.disconnect()
    
    def get_connection_status(self) -> Dict[str, bool]:
        """Get connection status for all clients."""
        return {z: c.is_connected() for z, c in self.clients.items()}