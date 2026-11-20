"""
MQ135 Air Quality Sensor Driver
MicroPython compatible
Measures CO2, NH3, NOx, alcohol, benzene, smoke, CO
"""

import machine
import time
import math
from typing import Optional
from ..config import (
    MQ135_PIN, MQ135_RL, MQ135_RO_CLEAN_AIR, MQ135_WARMUP_TIME_MS,
    VALIDATION_RANGES, load_calibration, save_calibration
)


class MQ135Sensor:
    """MQ135 gas sensor driver with warm-up, calibration, and ppm calculation."""
    
    # Gas curves: (a, b) for ppm = a * (Rs/Ro)^b
    # Approximate curves for different gases
    GAS_CURVES = {
        'co2': (110.47, -2.862),
        'co': (605.18, -3.937),
        'alcohol': (77.255, -3.18),
        'nh3': (102.2, -2.473),
        'benzene': (34.668, -3.369),
        'smoke': (197.16, -2.842),
    }
    
    # Default to CO2 equivalent (most common for air quality index)
    DEFAULT_GAS = 'co2'
    
    def __init__(self, pin: int = MQ135_PIN, rl: float = MQ135_RL):
        self.pin = pin
        self.rl = rl  # Load resistance in kOhms
        self.adc = machine.ADC(machine.Pin(pin))
        self.adc.atten(machine.ADC.ATTN_11DB)  # 0-3.3V range
        self.adc.width(machine.ADC.WIDTH_12BIT)  # 12-bit (0-4095)
        
        # Calibration
        cal = load_calibration()
        self.ro = cal.get('mq135_ro', MQ135_RO_CLEAN_AIR)  # Ro in kOhms
        self._is_calibrated = 'mq135_ro' in cal
        self._warmup_complete = False
        self._warmup_start = time.ticks_ms()
        self._last_read = 0
        self._last_ppm = None
        self._consecutive_errors = 0
        
    def warmup(self) -> bool:
        """
        Run warm-up sequence. Must be called repeatedly until returns True.
        Returns True when warm-up is complete.
        """
        if self._warmup_complete:
            return True
            
        elapsed = time.ticks_diff(time.ticks_ms(), self._warmup_start)
        if elapsed >= MQ135_WARMUP_TIME_MS:
            self._warmup_complete = True
            print(f"MQ135 warm-up complete after {elapsed/1000:.1f}s")
            # Auto-calibrate in clean air if not calibrated
            if not self._is_calibrated:
                self.calibrate_clean_air()
            return True
            
        # Show progress every 30 seconds
        if elapsed % 30000 < 100:
            remaining = (MQ135_WARMUP_TIME_MS - elapsed) / 1000
            print(f"MQ135 warming up... {remaining:.0f}s remaining")
        return False
    
    def read_raw(self) -> Optional[int]:
        """Read raw ADC value (0-4095)."""
        try:
            return self.adc.read()
        except Exception as e:
            self._consecutive_errors += 1
            print(f"MQ135 ADC read error: {e}")
            return None
    
    def read_resistance(self) -> Optional[float]:
        """
        Calculate sensor resistance Rs in kOhms.
        Rs = RL * (Vcc/ADC - 1)
        """
        raw = self.read_raw()
        if raw is None or raw == 0:
            return None
            
        # Vcc = 3.3V, ADC max = 4095
        voltage = (raw / 4095.0) * 3.3
        if voltage <= 0 or voltage >= 3.3:
            return None
            
        rs = self.rl * ((3.3 / voltage) - 1.0)
        return rs
    
    def read_ppm(self, gas: str = DEFAULT_GAS) -> Optional[float]:
        """
        Read gas concentration in ppm.
        Uses calibrated Ro and gas-specific curve.
        """
        if not self._warmup_complete:
            return None
            
        rs = self.read_resistance()
        if rs is None:
            return None
            
        ratio = rs / self.ro
        if ratio <= 0:
            return None
            
        a, b = self.GAS_CURVES.get(gas, self.GAS_CURVES[self.DEFAULT_GAS])
        ppm = a * (ratio ** b)
        
        # Validate
        if not (VALIDATION_RANGES['air_quality'][0] <= ppm <= VALIDATION_RANGES['air_quality'][1]):
            return None
            
        self._last_ppm = ppm
        self._consecutive_errors = 0
        return ppm
    
    def calibrate_clean_air(self, samples: int = 50, delay_ms: int = 100) -> bool:
        """
        Calibrate Ro in clean air.
        Should be run after warm-up in known clean environment.
        """
        print("Calibrating MQ135 in clean air...")
        rs_sum = 0.0
        valid_samples = 0
        
        for _ in range(samples):
            rs = self.read_resistance()
            if rs is not None:
                rs_sum += rs
                valid_samples += 1
            time.sleep_ms(delay_ms)
            
        if valid_samples < samples // 2:
            print(f"Calibration failed: only {valid_samples}/{samples} valid samples")
            return False
            
        self.ro = rs_sum / valid_samples
        self._is_calibrated = True
        
        # Save to NVS
        cal = load_calibration()
        cal['mq135_ro'] = self.ro
        save_calibration(cal)
        
        print(f"MQ135 calibrated: Ro = {self.ro:.2f} kOhms")
        return True
    
    def get_status(self) -> dict:
        """Get sensor status for diagnostics."""
        return {
            'warmup_complete': self._warmup_complete,
            'calibrated': self._is_calibrated,
            'ro_kohms': self.ro,
            'last_ppm': self._last_ppm,
            'errors': self._consecutive_errors,
        }