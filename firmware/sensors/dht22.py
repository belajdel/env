"""
DHT22 Temperature & Humidity Sensor Driver
MicroPython compatible
"""

import dht
import machine
import time
from typing import Optional, Tuple
from ..config import DHT22_PIN, VALIDATION_RANGES


class DHT22Sensor:
    """DHT22 sensor driver with error handling and validation."""
    
    def __init__(self, pin: int = DHT22_PIN):
        self.pin = pin
        self.sensor = dht.DHT22(machine.Pin(pin))
        self._last_read = 0
        self._last_temp = None
        self._last_humidity = None
        self._consecutive_errors = 0
        self._max_errors = 5
        
    def read(self) -> Optional[Tuple[float, float]]:
        """
        Read temperature and humidity.
        Returns (temperature_c, humidity_pct) or None on failure.
        """
        # DHT22 needs at least 2 seconds between reads
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_read) < 2000:
            if self._last_temp is not None and self._last_humidity is not None:
                return (self._last_temp, self._last_humidity)
            # Wait if we don't have cached values
            time.sleep_ms(2000 - time.ticks_diff(now, self._last_read))
        
        try:
            self.sensor.measure()
            temp = self.sensor.temperature()
            hum = self.sensor.humidity()
            
            # Validate ranges
            if not (VALIDATION_RANGES['temperature'][0] <= temp <= VALIDATION_RANGES['temperature'][1]):
                raise ValueError(f"Temperature out of range: {temp}")
            if not (VALIDATION_RANGES['humidity'][0] <= hum <= VALIDATION_RANGES['humidity'][1]):
                raise ValueError(f"Humidity out of range: {hum}")
            
            self._last_read = now
            self._last_temp = temp
            self._last_humidity = hum
            self._consecutive_errors = 0
            
            return (temp, hum)
            
        except (OSError, ValueError) as e:
            self._consecutive_errors += 1
            print(f"DHT22 read error ({self._consecutive_errors}/{self._max_errors}): {e}")
            
            if self._consecutive_errors >= self._max_errors:
                # Sensor may be disconnected, reset
                self._reset_sensor()
                
            return None
    
    def read_temperature(self) -> Optional[float]:
        """Read only temperature."""
        result = self.read()
        return result[0] if result else None
    
    def read_humidity(self) -> Optional[float]:
        """Read only humidity."""
        result = self.read()
        return result[1] if result else None
    
    def _reset_sensor(self) -> None:
        """Reinitialize sensor after repeated errors."""
        try:
            self.sensor = dht.DHT22(machine.Pin(self.pin))
            self._consecutive_errors = 0
            print("DHT22 sensor reinitialized")
        except Exception as e:
            print(f"DHT22 reinit failed: {e}")
    
    def is_healthy(self) -> bool:
        """Check if sensor is responding."""
        return self._consecutive_errors < self._max_errors