"""
MAX4466 Electret Microphone Amplifier - Noise Level Sensor
MicroPython compatible
Estimates dB SPL from ADC samples
"""

import machine
import time
import math
import array
from typing import Optional
from ..config import (
    MAX4466_PIN, MAX4466_SAMPLE_RATE, MAX4466_SAMPLE_DURATION_MS,
    MAX4466_VREF, MAX4466_SENSITIVITY_DB, MAX4466_GAIN_DB,
    VALIDATION_RANGES, load_calibration, save_calibration
)


class MAX4466Sensor:
    """MAX4466 microphone amplifier driver for noise level estimation."""
    
    def __init__(self, pin: int = MAX4466_PIN):
        self.pin = pin
        self.adc = machine.ADC(machine.Pin(pin))
        self.adc.atten(machine.ADC.ATTN_11DB)  # 0-3.3V
        self.adc.width(machine.ADC.WIDTH_12BIT)  # 12-bit
        
        # Calibration
        cal = load_calibration()
        self.baseline_db = cal.get('max4466_baseline_db', 40.0)
        self._is_calibrated = 'max4466_baseline_db' in cal
        
        self._last_db = None
        self._consecutive_errors = 0
        self._vref = MAX4466_VREF
        self._adc_max = 4095
        self._adc_mid = self._adc_max // 2  # ~2048 for 1.65V bias
        
        # Sampling parameters
        self.sample_rate = MAX4466_SAMPLE_RATE
        self.sample_duration_ms = MAX4466_SAMPLE_DURATION_MS
        self.num_samples = int(self.sample_rate * self.sample_duration_ms / 1000)
        self.sample_interval_us = 1_000_000 // self.sample_rate
        
    def read_samples(self) -> Optional[array.array]:
        """Read raw ADC samples into array for efficient processing."""
        try:
            samples = array.array('H', [0]) * self.num_samples
            start = time.ticks_us()
            
            for i in range(self.num_samples):
                samples[i] = self.adc.read()
                target = start + (i + 1) * self.sample_interval_us
                while time.ticks_diff(target, time.ticks_us()) > 0:
                    pass
                    
            return samples
        except Exception as e:
            self._consecutive_errors += 1
            print(f"MAX4466 sampling error: {e}")
            return None
    
    def read_db_spl(self) -> Optional[float]:
        """
        Estimate sound pressure level in dB SPL.
        Uses RMS of AC component, calibrated against known reference.
        """
        samples = self.read_samples()
        if samples is None:
            return None
            
        # Convert to voltage, remove DC bias
        voltages = array.array('f', [0]) * self.num_samples
        sum_v = 0.0
        for i, s in enumerate(samples):
            v = (s / self._adc_max) * self._vref
            voltages[i] = v
            sum_v += v
            
        dc_bias = sum_v / self.num_samples
        
        # Calculate RMS of AC component
        squared_sum = 0.0
        for v in voltages:
            ac = v - dc_bias
            squared_sum += ac * ac
            
        vrms = math.sqrt(squared_sum / self.num_samples)
        
        # Convert to dB
        # MIC sensitivity: -44 dBV/Pa = 0.0063 V/Pa
        # Amplifier gain: 60 dB = 1000x
        # So output voltage per Pa = 0.0063 * 1000 = 6.3 V/Pa
        # But we measure Vrms, so Pa = Vrms / 6.3
        # dB SPL = 20 * log10(Pa / 20µPa) = 20 * log10(Pa) + 94
        # Combined: dB = 20 * log10(Vrms / 6.3) + 94
        # With calibration offset
        
        if vrms <= 0:
            return None
            
        # Reference: 94 dB SPL = 1 Pa = 6.3V at output (theoretical)
        # But actual sensitivity varies, so use calibration
        db = 20 * math.log10(vrms) + self.baseline_db
        
        # Validate
        if not (VALIDATION_RANGES['noise'][0] <= db <= VALIDATION_RANGES['noise'][1]):
            return None
            
        self._last_db = db
        self._consecutive_errors = 0
        return db
    
    def calibrate(self, reference_db: float) -> bool:
        """
        Calibrate against known sound level (e.g., 94 dB calibrator).
        Adjusts baseline_db so that read_db_spl() returns reference_db.
        """
        print(f"Calibrating MAX4466 at {reference_db} dB SPL...")
        
        samples = self.read_samples()
        if samples is None:
            return False
            
        # Calculate Vrms
        voltages = array.array('f', [0]) * self.num_samples
        sum_v = 0.0
        for i, s in enumerate(samples):
            v = (s / self._adc_max) * self._vref
            voltages[i] = v
            sum_v += v
            
        dc_bias = sum_v / self.num_samples
        squared_sum = 0.0
        for v in voltages:
            ac = v - dc_bias
            squared_sum += ac * ac
            
        vrms = math.sqrt(squared_sum / self.num_samples)
        
        if vrms <= 0:
            print("Calibration failed: zero RMS voltage")
            return False
            
        # New baseline: reference_db = 20*log10(vrms) + baseline
        # baseline = reference_db - 20*log10(vrms)
        new_baseline = reference_db - 20 * math.log10(vrms)
        
        self.baseline_db = new_baseline
        self._is_calibrated = True
        
        cal = load_calibration()
        cal['max4466_baseline_db'] = self.baseline_db
        save_calibration(cal)
        
        print(f"MAX4466 calibrated: baseline = {self.baseline_db:.1f} dB")
        return True
    
    def get_status(self) -> dict:
        """Get sensor status."""
        return {
            'calibrated': self._is_calibrated,
            'baseline_db': self.baseline_db,
            'last_db': self._last_db,
            'errors': self._consecutive_errors,
        }