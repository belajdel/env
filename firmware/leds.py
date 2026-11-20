"""
LED Status Indicators
MicroPython compatible
"""

import machine
import time
from ..config import LED_WIFI_PIN, LED_MQTT_PIN, LED_ALERT_PIN, RELAY_ACTIVE_LOW


class StatusLED:
    """Single status LED with blink patterns."""
    
    def __init__(self, pin: int, active_low: bool = False):
        self.pin = machine.Pin(pin, machine.Pin.OUT)
        self.active_low = active_low
        self._state = False
        self._blink_task = None
        self._blink_pattern = None
        self._blink_index = 0
        self._last_blink = 0
        self.off()  # Initialize to off
        
    def on(self) -> None:
        """Turn LED on."""
        self._state = True
        self.pin.value(0 if self.active_low else 1)
        
    def off(self) -> None:
        """Turn LED off."""
        self._state = False
        self.pin.value(1 if self.active_low else 0)
        
    def toggle(self) -> None:
        """Toggle LED state."""
        if self._state:
            self.off()
        else:
            self.on()
            
    def set(self, state: bool) -> None:
        """Set LED state."""
        if state:
            self.on()
        else:
            self.off()
            
    def blink(self, pattern: list = None, interval: int = 500) -> None:
        """
        Start blinking with pattern.
        pattern: list of (on_time_ms, off_time_ms) tuples, or None for simple blink
        interval: simple blink interval if pattern is None
        """
        if pattern is None:
            pattern = [(interval, interval)]
        self._blink_pattern = pattern
        self._blink_index = 0
        self._last_blink = time.ticks_ms()
        self.on()  # Start with on
        
    def update(self) -> None:
        """Update blink state (call in main loop)."""
        if not self._blink_pattern:
            return
            
        now = time.ticks_ms()
        on_time, off_time = self._blink_pattern[self._blink_index]
        
        if self._state:
            # LED is on, check if should turn off
            if time.ticks_diff(now, self._last_blink) >= on_time:
                self.off()
                self._last_blink = now
        else:
            # LED is off, check if should turn on
            if time.ticks_diff(now, self._last_blink) >= off_time:
                self.on()
                self._last_blink = now
                # Move to next pattern step
                self._blink_index = (self._blink_index + 1) % len(self._blink_pattern)
                
    def stop_blink(self, final_state: bool = False) -> None:
        """Stop blinking and set final state."""
        self._blink_pattern = None
        self.set(final_state)


class LEDManager:
    """Manages all status LEDs for the monitoring device."""
    
    def __init__(self):
        self.wifi = StatusLED(LED_WIFI_PIN, active_low=RELAY_ACTIVE_LOW)
        self.mqtt = StatusLED(LED_MQTT_PIN, active_low=RELAY_ACTIVE_LOW)
        self.alert = StatusLED(LED_ALERT_PIN, active_low=RELAY_ACTIVE_LOW)
        self._all_leds = [self.wifi, self.mqtt, self.alert]
        
    def update_all(self) -> None:
        """Update all LED blink states."""
        for led in self._all_leds:
            led.update()
            
    def set_wifi_status(self, connected: bool, connecting: bool = False) -> None:
        """Set WiFi LED status."""
        if connecting:
            self.wifi.blink([(200, 200)])  # Fast blink while connecting
        elif connected:
            self.wifi.on()
        else:
            self.wifi.off()
            
    def set_mqtt_status(self, connected: bool, connecting: bool = False, 
                        reconnecting: bool = False) -> None:
        """Set MQTT LED status."""
        if connecting or reconnecting:
            self.mqtt.blink([(500, 500)])  # Slow blink while connecting/reconnecting
        elif connected:
            self.mqtt.on()
        else:
            self.mqtt.off()
            
    def set_alert_status(self, active: bool, level: str = "warning") -> None:
        """Set alert LED status."""
        if active:
            if level == "critical":
                self.alert.blink([(100, 100)])  # Fast blink for critical
            elif level == "warning":
                self.alert.blink([(500, 500)])  # Slow blink for warning
            else:
                self.alert.on()  # Solid for info
        else:
            self.alert.off()
            
    def startup_sequence(self) -> None:
        """Run startup LED sequence."""
        for led in self._all_leds:
            led.on()
            time.sleep_ms(100)
        time.sleep_ms(200)
        for led in self._all_leds:
            led.off()
            time.sleep_ms(100)
        # All on briefly
        for led in self._all_leds:
            led.on()
        time.sleep_ms(500)
        for led in self._all_leds:
            led.off()
            
    def error_pattern(self, error_code: int) -> None:
        """Show error code via blink pattern (for diagnostics)."""
        # Turn off all
        for led in self._all_leds:
            led.off()
        time.sleep_ms(500)
        # Blink error code on alert LED
        for i in range(error_code):
            self.alert.on()
            time.sleep_ms(200)
            self.alert.off()
            time.sleep_ms(200)
        time.sleep_ms(1000)