"""
Relay Control Handler
MicroPython compatible
Controls 2 relays with command handling and safety features
"""

import machine
import time
import json
from typing import Optional, Dict, Callable
from ..config import RELAY_1_PIN, RELAY_2_PIN, RELAY_ACTIVE_LOW, TOPIC_RELAY_CMD, TOPIC_RELAY_STATE, TOPIC_BASE


class Relay:
    """Single relay with state tracking and safety features."""
    
    def __init__(self, pin: int, relay_id: int, active_low: bool = RELAY_ACTIVE_LOW):
        self.pin = machine.Pin(pin, machine.Pin.OUT)
        self.relay_id = relay_id
        self.active_low = active_low
        self._state = False
        self._last_change = 0
        self._min_interval_ms = 1000  # Minimum 1 second between changes
        self._max_on_time_ms = 3600000  # Max 1 hour on without refresh
        self._auto_off_enabled = True
        self.off()  # Initialize to safe state (off)
        
    def on(self) -> bool:
        """Turn relay on. Returns True if state changed."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_change) < self._min_interval_ms:
            return False
        self._state = True
        self.pin.value(0 if self.active_low else 1)
        self._last_change = now
        return True
        
    def off(self) -> bool:
        """Turn relay off. Returns True if state changed."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_change) < self._min_interval_ms:
            return False
        self._state = False
        self.pin.value(1 if self.active_low else 0)
        self._last_change = now
        return True
        
    def toggle(self) -> bool:
        """Toggle relay state."""
        if self._state:
            return self.off()
        return self.on()
        
    def set(self, state: bool) -> bool:
        """Set relay state explicitly."""
        if state:
            return self.on()
        return self.off()
        
    def get_state(self) -> bool:
        """Get current relay state."""
        return self._state
    
    def get_state_str(self) -> str:
        """Get state as string."""
        return "on" if self._state else "off"
    
    def check_auto_off(self) -> bool:
        """Check and enforce max on time. Returns True if turned off."""
        if self._auto_off_enabled and self._state:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_change) >= self._max_on_time_ms:
                print(f"Relay {self.relay_id}: Auto-off after max on time")
                return self.off()
        return False
    
    def disable_auto_off(self) -> None:
        """Disable auto-off (use with caution)."""
        self._auto_off_enabled = False
        
    def enable_auto_off(self) -> None:
        """Enable auto-off."""
        self._auto_off_enabled = True


class RelayManager:
    """Manages both relays and handles MQTT commands."""
    
    def __init__(self, mqtt_client=None):
        self.relay1 = Relay(RELAY_1_PIN, 1)
        self.relay2 = Relay(RELAY_2_PIN, 2)
        self.relays = {1: self.relay1, 2: self.relay2}
        self.mqtt_client = mqtt_client
        self._command_callback = None
        self._state_publish_callback = None
        
    def set_mqtt_client(self, client) -> None:
        """Set MQTT client for publishing state."""
        self.mqtt_client = client
        
    def set_state_publish_callback(self, callback: Callable[[int, bool], None]) -> None:
        """Set callback for state publishing (topic, payload)."""
        self._state_publish_callback = callback
        
    def handle_command(self, relay_id: int, command: str, payload: dict = None) -> Dict:
        """
        Handle relay command from MQTT.
        Returns result dict with success, state, message.
        """
        if relay_id not in self.relays:
            return {"success": False, "error": f"Invalid relay ID: {relay_id}"}
            
        relay = self.relays[relay_id]
        previous_state = relay.get_state()
        
        try:
            if command == "on":
                success = relay.on()
                message = "Relay turned on"
            elif command == "off":
                success = relay.off()
                message = "Relay turned off"
            elif command == "toggle":
                success = relay.toggle()
                message = "Relay toggled"
            elif command == "state":
                success = True
                message = "State requested"
            else:
                return {"success": False, "error": f"Unknown command: {command}"}
                
            new_state = relay.get_state()
            
            # Publish state change if callback set
            if self._state_publish_callback and new_state != previous_state:
                self._state_publish_callback(relay_id, new_state)
                
            return {
                "success": success,
                "relay_id": relay_id,
                "state": new_state,
                "previous_state": previous_state,
                "message": message,
                "timestamp": time.time()
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def publish_state(self, relay_id: int) -> None:
        """Publish current state of a relay."""
        if relay_id in self.relays and self._state_publish_callback:
            self._state_publish_callback(relay_id, self.relays[relay_id].get_state())
            
    def publish_all_states(self) -> None:
        """Publish state of all relays."""
        for rid in self.relays:
            self.publish_state(rid)
            
    def get_all_states(self) -> Dict:
        """Get all relay states."""
        return {rid: relay.get_state() for rid, relay in self.relays.items()}
    
    def safety_check(self) -> None:
        """Run periodic safety checks (auto-off, etc.)."""
        for relay in self.relays.values():
            relay.check_auto_off()
            
    def emergency_off(self) -> None:
        """Emergency off - turn off all relays immediately."""
        for relay in self.relays.values():
            relay.off()
        self.publish_all_states()
        print("EMERGENCY: All relays turned off")
        
    def get_status(self) -> Dict:
        """Get status of all relays for diagnostics."""
        return {
            rid: {
                "state": relay.get_state(),
                "state_str": relay.get_state_str(),
                "last_change_ms": relay._last_change,
                "auto_off_enabled": relay._auto_off_enabled,
            }
            for rid, relay in self.relays.items()
        }


def create_relay_command_handler(relay_manager: RelayManager):
    """Create MQTT message handler for relay commands."""
    
    def handle_relay_message(topic: str, msg: bytes) -> None:
        """
        Handle incoming relay command message.
        Topic format: factory/{zone_id}/relay/{relay_id}/cmd
        Payload: {"command": "on|off|toggle|state", "params": {...}}
        """
        try:
            # Parse topic to get relay_id
            parts = topic.split('/')
            if len(parts) != 5 or parts[3] != 'relay':
                print(f"Invalid relay topic: {topic}")
                return
                
            relay_id = int(parts[4])
            
            # Parse payload
            payload = json.loads(msg.decode('utf-8'))
            command = payload.get('command', '').lower()
            
            if not command:
                print("Missing command in relay payload")
                return
                
            # Handle command
            result = relay_manager.handle_command(relay_id, command, payload)
            
            # Log result
            if result.get('success'):
                print(f"Relay {relay_id} {command}: {result.get('message')}")
            else:
                print(f"Relay {relay_id} {command} failed: {result.get('error')}")
                
        except json.JSONDecodeError:
            print(f"Invalid JSON in relay command: {msg}")
        except ValueError:
            print(f"Invalid relay ID in topic: {topic}")
        except Exception as e:
            print(f"Relay command handler error: {e}")
            
    return handle_relay_message