"""
ZMPT101B AC Voltage Sensor Driver
MicroPython compatible
Measures RMS voltage via ADC sampling
"""

import machine
import time
import math
from typing import Optional
from ..config import (
    ZMPT101B_PIN, ZMPT101B_SAMPLES_PER_CYCLE, ZMPT101B_CYCLES_TO_SAMPLE,
    ZMPT101B_CALIBRATION_FACTOR, ZMPT101B_OFFSET,
    VALIDATION_RANGES, load_calibration, save_calibration
)


class ZMPT101BSensor:
    """ZMPT101B AC voltage sensor driver with RMS calculation."""
    
    # AC frequency (assume 50Hz or 60Hz)
    AC_FREQUENCY = 50  # Hz
    SAMPLE_INTERVAL_US = int(1_000_000 / (AC_FREQUENCY * ZMPT101B_SAMPLES_PER_CYCLE))
    
    def __init__(self, pin: int = ZMPT101B_PIN):
        self.pin = pin
        self.adc = machine.ADC(machine.Pin(pin))
        self.adc.atten(machine.ADC.ATTN_11DB)  # 0-3.3V
        self.adc.width(machine.ADC.WIDTH_12BIT)  # 12-bit
        
        # Calibration
        cal = load_calibration()
        self.calibration_factor = cal.get('zmpt101b_factor', ZMPT101B_CALIBRATION_FACTOR)
        self.offset = cal.get('zmpt101b_offset', ZMPT101B_OFFSET)
        self._is_calibrated = 'zmpt101b_factor' in cal
        
        self._last_voltage = None
        self._consecutive_errors = 0
        self._vref = 3.3
        self._adc_max = 4095
        
    def read_raw_samples(self, num_samples: int = None) -> list:
        """
        Read raw ADC samples over multiple AC cycles.
        Returns list of raw ADC values.
        """
        if num_samples is None:
            num_samples = ZMPT101B_SAMPLES_PER_CYCLE * ZMPT101B_CYCLES_TO_SAMPLE
            
        samples = []
        start = time.ticks_us()
        
        for i in range(num_samples):
            samples.append(self.adc.read())
            # Busy wait for precise timing
            target = start + (i + 1) * self.SAMPLE_INTERVAL_US
            while time.ticks_diff(target, time.ticks_us()) > 0:
                pass
                
        return samples
    
    def read_voltage_rms(self) -> Optional[float]:
        """
        Calculate RMS voltage from ADC samples.
        V_rms = (V_adc_rms - offset) * calibration_factor
        """
        try:
            samples = self.read_raw_samples()
            if not samples:
                return None
                
            # Convert to voltage
            voltages = [(s / self._adc_max) * self._vref for s in samples]
            
            # Remove DC offset (midpoint)
            mean_v = sum(voltages) / len(voltages)
            ac_voltages = [v - mean_v for v in voltages]
            
            # Calculate RMS
            squared_sum = sum(v * v for v in ac_voltages)
            vrms_adc = math.sqrt(squared_sum / len(ac_voltages))
            
            # Apply calibration
            voltage = (vrms_adc - self.offset) * self.calibration_factor
            
            # Validate
            if not (VALIDATION_RANGES['voltage'][0] <= voltage <= VALIDATION_RANGES['voltage'][1]):
                return None
                
            self._last_voltage = voltage
            self._consecutive_errors = 0
            return voltage
            
        except Exception as e:
            self._consecutive_errors += 1
            print(f"ZMPT101B read error: {e}")
            return None
    
    def calibrate(self, known_voltage: float, samples: int = 5) -> bool:
        """
        Calibrate sensor against known AC voltage.
        Should be run with a reference multimeter.
        """
        print(f"Calibrating ZMPT101B with known voltage: {known_voltage}V")
        
        vrms_readings = []
        for _ in range(samples):
            v = self.read_voltage_rms()
            if v is not None:
                vrms_readings.append(v)
            time.sleep(1)
            
        if len(vrms_readings) < samples // 2:
            print("Calibration failed: insufficient valid readings")
            return False
            
        avg_measured = sum(vrms_readings) / len(vrms_readings)
        
        # Calculate new calibration factor
        # measured = (vrms_adc - offset) * factor
        # We know the actual voltage, so factor = actual / (vrms_adc - offset)
        # But we need to re-measure vrms_adc without factor applied
        raw_samples = self.read_raw_samples()
        voltages = [(s / self._adc_max) * self._vref for s in raw_samples]
        mean_v = sum(voltages) / len(voltages)
        ac_voltages = [v - mean_v for v in voltages]
        squared_sum = sum(v * v for v in ac_voltages)
        vrms_adc = math.sqrt(squared_sum / len(ac_voltages))
        
        new_factor = known_voltage / (vrms_adc - self.offset) if (vrms_adc - self.offset) != 0 else 1.0
        
        self.calibration_factor = new_factor
        self._is_calibrated = True
        
        # Save to NVS
        cal = load_calibration()
        cal['zmpt101b_factor'] = self.calibration_factor
        save_calibration(cal)
        
        print(f"ZMPT101B calibrated: factor = {self.calibration_factor:.4f}")
        return True
    
    def calibrate_offset(self) -> bool:
        """Calibrate DC offset (run with no AC voltage applied)."""
        print("Calibrating ZMPT101B offset (ensure no AC voltage)...")
        
        raw_samples = self.read_raw_samples()
        voltages = [(s / self._adc_max) * self._vref for s in raw_samples]
        mean_v = sum(voltages) / len(voltages)
        
        self.offset = mean_v
        
        cal = load_calibration()
        cal['zmpt101b_offset'] = self.offset
        save_calibration(cal)
        
        print(f"ZMPT101B offset calibrated: {self.offset:.4f}V")
        return True
    
    def get_status(self) -> dict:
        """Get sensor status."""
        return {
            'calibrated': self._is_calibrated,
            'calibration_factor': self.calibration_factor,
            'offset': self.offset,
            'last_voltage': self._last_voltage,
            'errors': self._consecutive_errors,
        }