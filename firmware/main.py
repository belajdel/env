"""
Main Firmware Application for ESP32 Environmental Monitoring Device
MicroPython 1.20+ compatible
"""

import time
import machine
import gc
import json
import sys
from typing import Optional, Dict, Any

# Import modules
from config import (
    DEVICE_ID, ZONE_ID, FIRMWARE_VERSION, SAMPLING_INTERVAL_MS,
    AGGREGATION_INTERVAL_MS, VALID_PARAMETERS, PARAMETER_UNITS,
    TOPIC_RELAY_CMD, WDT_TIMEOUT_MS
)
from sensors import DHT22Sensor, MQ135Sensor, PMS5003Sensor, ZMPT101BSensor, MAX4466Sensor
from filters import MultiParameterFilter
from display import DisplayManager, LCD16x2
from leds import LEDManager
from relays import RelayManager, create_relay_command_handler
from mqtt_client import MQTTClient


class EnvMonitor:
    """Main environmental monitoring application."""
    
    def __init__(self):
        # Initialize hardware
        self._init_hardware()
        
        # Initialize sensors
        self._init_sensors()
        
        # Initialize filters
        self.filters = MultiParameterFilter(list(VALID_PARAMETERS))
        
        # Initialize MQTT
        self._init_mqtt()
        
        # Initialize display and LEDs
        self.display = DisplayManager(self.lcd)
        self.leds = LEDManager()
        
        # Initialize relays
        self.relays = RelayManager(self.mqtt)
        self.relays.set_state_publish_callback(self._publish_relay_state)
        
        # Set up MQTT message handler for relay commands
        self.mqtt.set_callbacks(message_callback=self._on_mqtt_message)
        
        # State
        self.running = False
        self.last_sample = 0
        self.last_aggregate = 0
        self.sample_count = 0
        self.aggregate_sum = {p: 0.0 for p in VALID_PARAMETERS}
        self.aggregate_count = {p: 0 for p in VALID_PARAMETERS}
        self.mqtt_connected = False
        self.wifi_connected = False
        self.alert_active = False
        self.alert_level = "info"
        
        # Watchdog
        self.wdt = None
        self._init_watchdog()
        
        print(f"Environmental Monitor initialized: {DEVICE_ID} v{FIRMWARE_VERSION}")
        
    def _init_hardware(self) -> None:
        """Initialize hardware peripherals."""
        # CPU frequency
        machine.freq(240_000_000)
        
        # I2C for LCD
        from config import LCD_SDA_PIN, LCD_SCL_PIN, LCD_I2C_ADDR
        self.i2c = machine.I2C(0, sda=machine.Pin(LCD_SDA_PIN), scl=machine.Pin(LCD_SCL_PIN), freq=100000)
        self.lcd = LCD16x2(i2c_addr=LCD_I2C_ADDR, sda_pin=LCD_SDA_PIN, scl_pin=LCD_SCL_PIN)
        
    def _init_sensors(self) -> None:
        """Initialize all sensors."""
        self.dht22 = DHT22Sensor()
        self.mq135 = MQ135Sensor()
        self.pms5003 = PMS5003Sensor()
        self.zmpt101b = ZMPT101BSensor()
        self.max4466 = MAX4466Sensor()
        
        # Warm up MQ135
        print("Starting MQ135 warm-up...")
        self.display.show_connecting("MQ135 Warm-up")
        
    def _init_mqtt(self) -> None:
        """Initialize MQTT client."""
        self.mqtt = MQTTClient()
        
    def _init_watchdog(self) -> None:
        """Initialize watchdog timer."""
        try:
            self.wdt = machine.WDT(timeout=WDT_TIMEOUT_MS)
            print("Watchdog initialized")
        except Exception as e:
            print(f"Watchdog init failed: {e}")
            
    def _feed_watchdog(self) -> None:
        """Feed watchdog timer."""
        if self.wdt:
            self.wdt.feed()
            
    def _publish_relay_state(self, relay_id: int, state: bool) -> None:
        """Publish relay state to MQTT."""
        topic = f"{TOPIC_RELAY_CMD.replace('+/cmd', f'{relay_id}/state')}"
        payload = json.dumps({
            "relay_id": relay_id,
            "state": "on" if state else "off",
            "timestamp": time.time()
        })
        self.mqtt.publish(topic, payload, qos=1, retain=True)
        
    def _on_mqtt_message(self, topic: str, msg: bytes) -> None:
        """Handle incoming MQTT messages."""
        # Handle relay commands
        if topic.startswith(f"factory/{ZONE_ID}/relay/") and topic.endswith("/cmd"):
            handler = create_relay_command_handler(self.relays)
            handler(topic, msg)
            
    def _connect_wifi(self) -> bool:
        """Connect to WiFi (placeholder - implement based on your network)."""
        # This is a placeholder. In production, use network.WLAN
        # For now, simulate connection
        import network
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        # WiFi credentials should be in config or NVS
        ssid = "YOUR_WIFI_SSID"
        password = "YOUR_WIFI_PASSWORD"
        
        if not wlan.isconnected():
            print("Connecting to WiFi...")
            self.leds.set_wifi_status(False, connecting=True)
            self.display.show_connecting("WiFi")
            wlan.connect(ssid, password)
            
            timeout = 20
            while not wlan.isconnected() and timeout > 0:
                time.sleep(1)
                timeout -= 1
                
        if wlan.isconnected():
            self.wifi_connected = True
            self.leds.set_wifi_status(True)
            print(f"WiFi connected: {wlan.ifconfig()}")
            return True
        else:
            self.wifi_connected = False
            self.leds.set_wifi_status(False)
            print("WiFi connection failed")
            return False
            
    def _connect_mqtt(self) -> bool:
        """Connect to MQTT broker."""
        if self.mqtt.connect():
            self.mqtt_connected = True
            self.leds.set_mqtt_status(True)
            
            # Subscribe to relay commands
            self.mqtt.subscribe(f"factory/{ZONE_ID}/relay/+/cmd")
            
            # Publish initial state
            self._publish_device_state()
            return True
        else:
            self.mqtt_connected = False
            self.leds.set_mqtt_status(False)
            return False
            
    def _publish_device_state(self) -> None:
        """Publish device state to MQTT."""
        state = {
            "device_id": DEVICE_ID,
            "zone_id": ZONE_ID,
            "firmware_version": FIRMWARE_VERSION,
            "uptime": time.ticks_ms() // 1000,
            "free_heap": gc.mem_free(),
            "sensors": {
                "dht22": self.dht22.is_healthy(),
                "mq135": self.mq135.get_status()['warmup_complete'],
                "pms5003": True,
                "zmpt101b": True,
                "max4466": True,
            },
            "relays": self.relays.get_all_states(),
        }
        self.mqtt._publish_state(state)
        
    def _read_all_sensors(self) -> Dict[str, Optional[float]]:
        """Read all sensors and return raw values."""
        readings = {}
        
        # DHT22: temperature and humidity
        dht_result = self.dht22.read()
        if dht_result:
            readings['temperature'] = dht_result[0]
            readings['humidity'] = dht_result[1]
            
        # MQ135: air quality (CO2 equivalent)
        if self.mq135._warmup_complete:
            aq = self.mq135.read_ppm()
            if aq is not None:
                readings['air_quality'] = aq
        else:
            # Still warming up
            self.mq135.warmup()
            
        # PMS5003: PM2.5 and PM10
        pms_result = self.pms5003.read()
        if pms_result:
            readings['pm10'] = pms_result[0]
            readings['pm25'] = pms_result[1]
            readings['pm100'] = pms_result[2]
            
        # ZMPT101B: voltage
        voltage = self.zmpt101b.read_voltage_rms()
        if voltage is not None:
            readings['voltage'] = voltage
            
        # MAX4466: noise
        noise = self.max4466.read_db_spl()
        if noise is not None:
            readings['noise'] = noise
            
        return readings
        
    def _process_readings(self, raw_readings: Dict) -> Dict:
        """Process readings through filters."""
        return self.filters.process_all(raw_readings)
        
    def _publish_measurements(self, filtered_readings: Dict) -> None:
        """Publish filtered measurements to MQTT."""
        for param, value in filtered_readings.items():
            if value is not None and param in PARAMETER_UNITS:
                self.mqtt.publish_measurement(param, value, PARAMETER_UNITS[param])
                
    def _aggregate_readings(self, filtered_readings: Dict) -> None:
        """Accumulate readings for 1-minute aggregation."""
        for param, value in filtered_readings.items():
            if value is not None and param in VALID_PARAMETERS:
                self.aggregate_sum[param] += value
                self.aggregate_count[param] += 1
                
    def _publish_aggregates(self) -> None:
        """Publish 1-minute aggregate values."""
        for param in VALID_PARAMETERS:
            count = self.aggregate_count[param]
            if count > 0:
                avg = self.aggregate_sum[param] / count
                self.mqtt.publish_measurement(param, avg, PARAMETER_UNITS[param])
                # Reset for next minute
                self.aggregate_sum[param] = 0.0
                self.aggregate_count[param] = 0
                
    def _check_alerts(self, readings: Dict) -> None:
        """Check for alert conditions (local threshold check)."""
        # This is a simplified local check; real alerting is done in backend
        # But we can show critical alerts on display/LEDs immediately
        from config import VALIDATION_RANGES
        
        critical_params = []
        warning_params = []
        
        for param, value in readings.items():
            if value is None:
                continue
                
            # Simple threshold checks (mirroring backend rules)
            if param == 'temperature':
                if value >= 35 or value <= 15:
                    critical_params.append(f"T:{value:.1f}C")
                elif value >= 28 or value <= 18:
                    warning_params.append(f"T:{value:.1f}C")
            elif param == 'humidity':
                if value >= 85 or value <= 20:
                    critical_params.append(f"H:{value:.0f}%")
                elif value >= 70 or value <= 30:
                    warning_params.append(f"H:{value:.0f}%")
            elif param == 'noise':
                if value >= 85:
                    critical_params.append(f"N:{value:.0f}dB")
                elif value >= 70:
                    warning_params.append(f"N:{value:.0f}dB")
            elif param == 'voltage':
                if value >= 270 or value <= 190:
                    critical_params.append(f"V:{value:.0f}V")
                elif value >= 260 or value <= 200:
                    warning_params.append(f"V:{value:.0f}V")
                    
        if critical_params:
            self.alert_active = True
            self.alert_level = "critical"
            msg = " ".join(critical_params[:2])
            self.display.show_alert(msg, "CRITICAL")
            self.leds.set_alert_status(True, "critical")
        elif warning_params:
            self.alert_active = True
            self.alert_level = "warning"
            self.leds.set_alert_status(True, "warning")
        else:
            self.alert_active = False
            self.alert_level = "info"
            self.leds.set_alert_status(False)
            
    def _update_display(self, readings: Dict) -> None:
        """Update LCD display."""
        self.display.show_status(
            wifi_connected=self.wifi_connected,
            mqtt_connected=self.mqtt_connected,
            alert_active=self.alert_active,
            readings=readings
        )
        
    def run(self) -> None:
        """Main run loop."""
        print("Starting main loop...")
        self.running = True
        
        # Startup sequence
        self.leds.startup_sequence()
        self.display.show_startup(DEVICE_ID, FIRMWARE_VERSION)
        
        # Connect WiFi
        self._connect_wifi()
        
        # Connect MQTT
        self._connect_mqtt()
        
        # Main loop
        while self.running:
            try:
                self._feed_watchdog()
                gc.collect()
                
                now = time.ticks_ms()
                
                # Check MQTT connection
                if not self.mqtt.check_connection():
                    self.mqtt_connected = False
                    self.leds.set_mqtt_status(False, reconnecting=True)
                elif not self.mqtt_connected:
                    self.mqtt_connected = True
                    self.leds.set_mqtt_status(True)
                    self._publish_device_state()
                    
                # Process MQTT messages
                self.mqtt.loop()
                
                # Safety check for relays
                self.relays.safety_check()
                
                # Update LEDs
                self.leds.update_all()
                
                # Sample sensors at interval
                if time.ticks_diff(now, self.last_sample) >= SAMPLING_INTERVAL_MS:
                    self.last_sample = now
                    
                    # Read sensors
                    raw = self._read_all_sensors()
                    
                    # Filter readings
                    filtered = self._process_readings(raw)
                    
                    # Publish measurements
                    self._publish_measurements(filtered)
                    
                    # Aggregate
                    self._aggregate_readings(filtered)
                    
                    # Check alerts
                    self._check_alerts(filtered)
                    
                    # Update display
                    self._update_display(filtered)
                    
                    self.sample_count += 1
                    
                # Publish aggregates every minute
                if time.ticks_diff(now, self.last_aggregate) >= AGGREGATION_INTERVAL_MS:
                    self.last_aggregate = now
                    self._publish_aggregates()
                    self._publish_device_state()
                    
                # Small delay to prevent busy loop
                time.sleep_ms(10)
                
            except KeyboardInterrupt:
                print("Interrupted")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                sys.print_exception(e)
                time.sleep(1)
                
        self.shutdown()
        
    def shutdown(self) -> None:
        """Graceful shutdown."""
        print("Shutting down...")
        self.running = False
        
        # Turn off relays
        self.relays.emergency_off()
        
        # Publish offline status
        self.mqtt._publish_status("offline", "shutdown")
        time.sleep_ms(100)
        
        # Disconnect MQTT
        self.mqtt.disconnect()
        
        # Turn off LEDs
        for led in [self.leds.wifi, self.leds.mqtt, self.leds.alert]:
            led.off()
            
        # Clear display
        self.lcd.clear()
        self.lcd.print_line(0, "Shutdown", 'center')
        self.lcd.print_line(1, "Complete", 'center')
        
        print("Shutdown complete")


def main():
    """Entry point."""
    try:
        monitor = EnvMonitor()
        monitor.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.print_exception(e)
        # Blink error pattern
        import machine
        led = machine.Pin(2, machine.Pin.OUT)
        for _ in range(10):
            led.on()
            time.sleep_ms(100)
            led.off()
            time.sleep_ms(100)


if __name__ == "__main__":
    main()