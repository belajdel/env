"""
Sensor Model for Environmental Monitoring Simulator
Generates realistic sensor readings with daily cycles, noise, drift, and anomalies.
"""

import math
import random
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from .config import (
    ZONES, ZONE_TYPES, BASE_VALUES, DAILY_AMPLITUDE, NOISE_STD,
    DRIFT_PER_DAY, VALID_PARAMETERS, PARAMETER_UNITS,
    ANOMALY_TYPES, ANOMALY_DEFAULTS, SEED
)


@dataclass
class AnomalyState:
    """Tracks active anomaly injection for a zone/parameter."""
    anomaly_type: str = ''
    start_time: float = 0
    duration: int = 0  # in samples
    magnitude: float = 0
    rate: float = 0
    probability: float = 0
    samples_remaining: int = 0
    stuck_value: Optional[float] = None
    
    def is_active(self) -> bool:
        return self.anomaly_type != '' and self.samples_remaining > 0
    
    def tick(self) -> None:
        if self.samples_remaining > 0:
            self.samples_remaining -= 1
            if self.samples_remaining <= 0:
                self.reset()
                
    def reset(self) -> None:
        self.anomaly_type = ''
        self.start_time = 0
        self.duration = 0
        self.magnitude = 0
        self.rate = 0
        self.probability = 0
        self.samples_remaining = 0
        self.stuck_value = None


class SensorModel:
    """Simulates a single sensor parameter with daily cycles, noise, drift, and anomalies."""
    
    def __init__(self, zone_id: str, parameter: str, seed: int = None):
        self.zone_id = zone_id
        self.parameter = parameter
        self.zone_type = ZONE_TYPES[zone_id]
        
        # Base configuration
        self.base_value = BASE_VALUES[self.zone_type][parameter]
        self.amplitude = DAILY_AMPLITUDE[self.zone_type][parameter]
        self.noise_std = NOISE_STD[parameter]
        self.drift_per_day = DRIFT_PER_DAY[parameter]
        self.unit = PARAMETER_UNITS[parameter]
        
        # Random state
        self.rng = random.Random()
        if seed is not None:
            self.rng.seed(seed + hash(f"{zone_id}_{parameter}") % 1000000)
        else:
            self.rng.seed(hash(f"{zone_id}_{parameter}_{time.time()}") % 1000000)
            
        # Drift state
        self.drift_accumulator = 0.0
        self.start_time = time.time()
        self.sample_count = 0
        
        # Anomaly state
        self.anomaly = AnomalyState()
        
        # For stuck anomaly
        self._last_normal_value = self.base_value
        
    def _daily_cycle(self, timestamp: float) -> float:
        """Calculate daily sinusoidal variation."""
        # Convert timestamp to hour of day (0-24)
        hour = (timestamp % 86400) / 3600.0
        # Peak at 14:00 (2 PM), trough at 02:00
        phase = (hour - 14) / 24.0 * 2 * math.pi
        return self.amplitude * math.sin(phase)
    
    def _drift(self, timestamp: float) -> float:
        """Calculate accumulated drift."""
        days_elapsed = (timestamp - self.start_time) / 86400.0
        return self.drift_per_day * days_elapsed
    
    def _noise(self) -> float:
        """Generate random noise."""
        return self.rng.gauss(0, self.noise_std)
    
    def _apply_anomaly(self, base_value: float, timestamp: float) -> float:
        """Apply active anomaly to value."""
        if not self.anomaly.is_active():
            return base_value
            
        if self.anomaly.anomaly_type == 'spike':
            # Sudden spike for a few samples
            return base_value + self.anomaly.magnitude * self.noise_std
            
        elif self.anomaly.anomaly_type == 'drift':
            # Gradual drift over time
            elapsed = self.anomaly.duration - self.anomaly.samples_remaining
            return base_value + self.anomaly.rate * self.noise_std * elapsed
            
        elif self.anomaly.anomaly_type == 'stuck':
            # Value stuck at a specific value
            if self.anomaly.stuck_value is None:
                self.anomaly.stuck_value = self._last_normal_value
            return self.anomaly.stuck_value
            
        elif self.anomaly.anomaly_type == 'dropout':
            # Random dropout (return None to indicate missing)
            if self.rng.random() < self.anomaly.probability:
                return None
            return base_value
            
        return base_value
    
    def inject_anomaly(self, anomaly_type: str, **params) -> bool:
        """Inject an anomaly into this sensor."""
        if anomaly_type not in ANOMALY_TYPES:
            return False
            
        defaults = ANOMALY_DEFAULTS.get(anomaly_type, {})
        
        self.anomaly.anomaly_type = anomaly_type
        self.anomaly.start_time = time.time()
        self.anomaly.duration = params.get('duration', defaults.get('duration', 10))
        self.anomaly.magnitude = params.get('magnitude', defaults.get('magnitude', 3.0))
        self.anomaly.rate = params.get('rate', defaults.get('rate', 0.5))
        self.anomaly.probability = params.get('probability', defaults.get('probability', 0.5))
        self.anomaly.samples_remaining = self.anomaly.duration
        self.anomaly.stuck_value = None
        
        # Capture last normal value for stuck anomaly
        if anomaly_type == 'stuck':
            self.anomaly.stuck_value = self._last_normal_value
            
        return True
    
    def clear_anomaly(self) -> None:
        """Clear any active anomaly."""
        self.anomaly.reset()
    
    def generate(self, timestamp: float = None) -> Optional[float]:
        """Generate a sensor reading at the given timestamp."""
        if timestamp is None:
            timestamp = time.time()
            
        self.sample_count += 1
        
        # Base value with daily cycle and drift
        daily = self._daily_cycle(timestamp)
        drift = self._drift(timestamp)
        noise = self._noise()
        
        base_value = self.base_value + daily + drift + noise
        
        # Store last normal value (before anomaly)
        if not self.anomaly.is_active() or self.anomaly.anomaly_type != 'stuck':
            self._last_normal_value = base_value
        
        # Apply anomaly
        value = self._apply_anomaly(base_value, timestamp)
        
        # Tick anomaly
        self.anomaly.tick()
        
        return value
    
    def get_status(self) -> Dict[str, Any]:
        """Get sensor model status for debugging."""
        return {
            'zone_id': self.zone_id,
            'parameter': self.parameter,
            'base_value': self.base_value,
            'sample_count': self.sample_count,
            'drift_accumulated': self._drift(time.time()),
            'anomaly_active': self.anomaly.is_active(),
            'anomaly_type': self.anomaly.anomaly_type,
            'anomaly_remaining': self.anomaly.samples_remaining,
        }


class ZoneSimulator:
    """Simulates all sensors for a single zone."""
    
    def __init__(self, zone_id: str, seed: int = None):
        self.zone_id = zone_id
        self.sensors = {}
        
        base_seed = seed if seed is not None else SEED
        for i, param in enumerate(VALID_PARAMETERS):
            sensor_seed = base_seed + hash(f"{zone_id}_{param}") % 1000000
            self.sensors[param] = SensorModel(zone_id, param, seed=sensor_seed)
            
    def generate_all(self, timestamp: float = None) -> Dict[str, Optional[float]]:
        """Generate readings for all parameters."""
        if timestamp is None:
            timestamp = time.time()
            
        readings = {}
        for param, sensor in self.sensors.items():
            readings[param] = sensor.generate(timestamp)
        return readings
    
    def inject_anomaly(self, parameter: str, anomaly_type: str, **params) -> bool:
        """Inject anomaly for a specific parameter."""
        if parameter not in self.sensors:
            return False
        return self.sensors[parameter].inject_anomaly(anomaly_type, **params)
    
    def clear_anomaly(self, parameter: str) -> None:
        """Clear anomaly for a specific parameter."""
        if parameter in self.sensors:
            self.sensors[parameter].clear_anomaly()
    
    def clear_all_anomalies(self) -> None:
        """Clear all anomalies for this zone."""
        for sensor in self.sensors.values():
            sensor.clear_anomaly()
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all sensors in zone."""
        return {
            'zone_id': self.zone_id,
            'sensors': {p: s.get_status() for p, s in self.sensors.items()}
        }


class MultiZoneSimulator:
    """Manages simulation for all 7 zones."""
    
    def __init__(self, seed: int = SEED):
        self.seed = seed
        self.zones = {}
        for i, zone_id in enumerate(ZONES):
            zone_seed = seed + i * 1000
            self.zones[zone_id] = ZoneSimulator(zone_id, seed=zone_seed)
            
    def generate_all_zones(self, timestamp: float = None) -> Dict[str, Dict[str, Optional[float]]]:
        """Generate readings for all zones."""
        if timestamp is None:
            timestamp = time.time()
            
        all_readings = {}
        for zone_id, simulator in self.zones.items():
            all_readings[zone_id] = simulator.generate_all(timestamp)
        return all_readings
    
    def inject_anomaly(self, zone_id: str, parameter: str, anomaly_type: str, **params) -> bool:
        """Inject anomaly for a zone/parameter."""
        if zone_id not in self.zones:
            return False
        return self.zones[zone_id].inject_anomaly(parameter, anomaly_type, **params)
    
    def clear_anomaly(self, zone_id: str, parameter: str) -> None:
        """Clear anomaly for a zone/parameter."""
        if zone_id in self.zones:
            self.zones[zone_id].clear_anomaly(parameter)
    
    def clear_all_anomalies(self) -> None:
        """Clear all anomalies across all zones."""
        for zone in self.zones.values():
            zone.clear_all_anomalies()
    
    def get_zone_status(self, zone_id: str) -> Dict[str, Any]:
        """Get status for a specific zone."""
        if zone_id in self.zones:
            return self.zones[zone_id].get_status()
        return {}
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status for all zones."""
        return {z: sim.get_status() for z, sim in self.zones.items()}