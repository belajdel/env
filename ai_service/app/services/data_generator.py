"""
Synthetic Data Generator
Generates realistic industrial environmental sensor data with daily cycles, drift, and anomalies.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import json

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ai import (
    SyntheticDataConfig, ZONE_PARAMETER_CONFIGS, PARAMETER_UNITS,
    PARAMETER_RANGES, DEFAULT_THRESHOLDS, TrainingDataInDB
)

logger = get_logger(__name__)


@dataclass
class GenerationContext:
    """Context for data generation across zones/parameters."""
    timestamps: np.ndarray
    hour_of_day: np.ndarray
    day_of_year: np.ndarray
    day_of_week: np.ndarray
    is_weekend: np.ndarray


class SyntheticDataGenerator:
    """
    Generates synthetic time-series data for industrial environmental monitoring.
    
    Features:
    - Daily/weekly seasonal patterns
    - Long-term drift
    - Cross-parameter correlations
    - Realistic anomalies with labels
    - Zone-specific baselines
    """
    
    def __init__(self, config: Optional[SyntheticDataConfig] = None):
        self.config = config or SyntheticDataConfig(
            seed=settings.SYNTHETIC_DATA_SEED,
            days=settings.SYNTHETIC_DAYS,
            sample_rate_minutes=settings.SYNTHETIC_SAMPLE_RATE_MINUTES,
        )
        self.rng = np.random.default_rng(self.config.seed)
        self.context: Optional[GenerationContext] = None
        
    def generate_all(self) -> List[TrainingDataInDB]:
        """Generate complete synthetic dataset for all zones and parameters."""
        logger.info("generating_synthetic_data", 
                    days=self.config.days, 
                    sample_rate=self.config.sample_rate_minutes,
                    zones=len(self.config.zones),
                    parameters=len(self.config.parameters))
        
        self._build_context()
        
        all_samples = []
        
        for zone_id in self.config.zones:
            zone_samples = self._generate_zone_data(zone_id)
            all_samples.extend(zone_samples)
        
        logger.info("synthetic_data_generated", total_samples=len(all_samples))
        return all_samples
    
    def _build_context(self) -> None:
        """Build shared time context for all generation."""
        start_time = datetime.now(timezone.utc) - timedelta(days=self.config.days)
        end_time = datetime.now(timezone.utc)
        
        # Generate timestamps
        freq_minutes = self.config.sample_rate_minutes
        total_minutes = int((end_time - start_time).total_seconds() / 60)
        n_samples = total_minutes // freq_minutes + 1
        
        timestamps = np.array([
            start_time + timedelta(minutes=i * freq_minutes)
            for i in range(n_samples)
        ])
        
        # Time features
        hour_of_day = np.array([ts.hour + ts.minute / 60 for ts in timestamps])
        day_of_year = np.array([ts.timetuple().tm_yday for ts in timestamps])
        day_of_week = np.array([ts.weekday() for ts in timestamps])  # 0=Monday
        is_weekend = (day_of_week >= 5).astype(float)
        
        self.context = GenerationContext(
            timestamps=timestamps,
            hour_of_day=hour_of_day,
            day_of_year=day_of_year,
            day_of_week=day_of_week,
            is_weekend=is_weekend,
        )
    
    def _generate_zone_data(self, zone_id: str) -> List[TrainingDataInDB]:
        """Generate data for a single zone across all parameters."""
        zone_config = ZONE_PARAMETER_CONFIGS.get(zone_id, {})
        zone_type = zone_config.get("type", "production")
        
        # Generate base signals for each parameter
        param_signals = {}
        for param in self.config.parameters:
            param_signals[param] = self._generate_parameter_signal(param, zone_config)
        
        # Add cross-parameter correlations
        param_signals = self._add_correlations(param_signals, zone_type)
        
        # Add anomalies
        param_signals, anomaly_labels = self._add_anomalies(param_signals, zone_id)
        
        # Create training samples
        samples = []
        n_samples = len(self.context.timestamps)
        
        for i in range(n_samples):
            timestamp = self.context.timestamps[i]
            
            for param in self.config.parameters:
                value = param_signals[param][i]
                is_anomaly = anomaly_labels[param][i]
                
                # Build feature vector (current + recent history + time features)
                features = self._build_features(param_signals, i, param)
                
                sample = TrainingDataInDB(
                    zone_id=zone_id,
                    parameter=param,
                    features=features,
                    label=int(is_anomaly),
                    timestamp=timestamp,
                    is_synthetic=True,
                )
                samples.append(sample)
        
        return samples
    
    def _generate_parameter_signal(self, param: str, zone_config: Dict) -> np.ndarray:
        """Generate base signal for a parameter."""
        n = len(self.context.timestamps)
        signal = np.zeros(n)
        
        if param == "temperature":
            signal = self._generate_temperature(zone_config)
        elif param == "humidity":
            signal = self._generate_humidity(zone_config)
        elif param == "noise":
            signal = self._generate_noise(zone_config)
        elif param == "air_quality":
            signal = self._generate_air_quality(zone_config)
        elif param == "pm25":
            signal = self._generate_pm25(zone_config)
        elif param == "pm10":
            signal = self._generate_pm10(zone_config)
        elif param == "voltage":
            signal = self._generate_voltage(zone_config)
        
        # Add long-term drift
        drift = self.config.drift_factor * np.arange(n)
        signal += drift * (signal.max() - signal.min()) if signal.max() > signal.min() else 0
        
        # Add noise
        noise_std = (signal.max() - signal.min()) * 0.02 if signal.max() > signal.min() else 0.1
        signal += self.rng.normal(0, noise_std, n)
        
        # Clip to valid range
        min_val, max_val = PARAMETER_RANGES[param]
        signal = np.clip(signal, min_val, max_val)
        
        return signal
    
    def _generate_temperature(self, zone_config: Dict) -> np.ndarray:
        """Generate temperature with daily cycle and seasonal variation."""
        n = len(self.context.timestamps)
        base = zone_config.get("base_temp", 22)
        variance = zone_config.get("temp_variance", 5)
        
        # Daily cycle (peak at 14:00, trough at 04:00)
        daily = variance * np.sin(2 * np.pi * (self.context.hour_of_day - 14) / 24)
        
        # Seasonal variation (summer hotter)
        seasonal = 3 * np.sin(2 * np.pi * (self.context.day_of_year - 172) / 365)
        
        # Weekend effect (slightly lower)
        weekend = -0.5 * self.context.is_weekend
        
        return base + daily + seasonal + weekend
    
    def _generate_humidity(self, zone_config: Dict) -> np.ndarray:
        """Generate humidity (inverse correlation with temperature)."""
        n = len(self.context.timestamps)
        base = zone_config.get("base_humidity", 50)
        variance = zone_config.get("humidity_variance", 10)
        
        # Daily cycle (opposite to temperature - higher at night)
        daily = variance * np.sin(2 * np.pi * (self.context.hour_of_day - 4) / 24)
        
        # Seasonal
        seasonal = -5 * np.sin(2 * np.pi * (self.context.day_of_year - 172) / 365)
        
        # Weekend
        weekend = 2 * self.context.is_weekend
        
        return base + daily + seasonal + weekend
    
    def _generate_noise(self, zone_config: Dict) -> np.ndarray:
        """Generate noise levels (higher during work hours)."""
        n = len(self.context.timestamps)
        base = 55  # dB
        
        # Work hours pattern (8-18 on weekdays)
        work_hours = ((self.context.hour_of_day >= 8) & (self.context.hour_of_day <= 18) & (self.context.is_weekend == 0)).astype(float)
        daily = 15 * work_hours + 3 * np.sin(2 * np.pi * self.context.hour_of_day / 24)
        
        # Random bursts
        bursts = self.rng.exponential(2, n) * (self.rng.random(n) < 0.02).astype(float)
        
        return base + daily + bursts
    
    def _generate_air_quality(self, zone_config: Dict) -> np.ndarray:
        """Generate AQI."""
        base = 45
        
        # Correlated with PM2.5 and PM10
        daily = 10 * np.sin(2 * np.pi * (self.context.hour_of_day - 6) / 24)
        traffic = 15 * ((self.context.hour_of_day >= 7) & (self.context.hour_of_day <= 9) | 
                        (self.context.hour_of_day >= 17) & (self.context.hour_of_day <= 19)).astype(float)
        
        return base + daily + traffic
    
    def _generate_pm25(self, zone_config: Dict) -> np.ndarray:
        """Generate PM2.5."""
        base = 12
        
        # Daily pattern with morning/evening peaks
        daily = 5 * np.sin(2 * np.pi * (self.context.hour_of_day - 6) / 24)
        traffic = 8 * ((self.context.hour_of_day >= 7) & (self.context.hour_of_day <= 9) | 
                       (self.context.hour_of_day >= 17) & (self.context.hour_of_day <= 19)).astype(float)
        
        return base + daily + traffic
    
    def _generate_pm10(self, zone_config: Dict) -> np.ndarray:
        """Generate PM10 (correlated with PM2.5)."""
        base = 25
        
        daily = 10 * np.sin(2 * np.pi * (self.context.hour_of_day - 6) / 24)
        traffic = 15 * ((self.context.hour_of_day >= 7) & (self.context.hour_of_day <= 9) | 
                        (self.context.hour_of_day >= 17) & (self.context.hour_of_day <= 19)).astype(float)
        
        return base + daily + traffic
    
    def _generate_voltage(self, zone_config: Dict) -> np.ndarray:
        """Generate voltage (stable with small variations)."""
        base = 230
        
        # Small daily variation (load)
        daily = 2 * np.sin(2 * np.pi * (self.context.hour_of_day - 12) / 24)
        
        # Random fluctuations
        noise = self.rng.normal(0, 0.5, len(self.context.timestamps))
        
        return base + daily + noise
    
    def _add_correlations(self, signals: Dict[str, np.ndarray], zone_type: str) -> Dict[str, np.ndarray]:
        """Add cross-parameter correlations."""
        strength = self.config.correlation_strength
        
        # Temperature-Humidity negative correlation
        if "temperature" in signals and "humidity" in signals:
            temp_norm = (signals["temperature"] - signals["temperature"].mean()) / (signals["temperature"].std() + 1e-8)
            signals["humidity"] -= strength * 0.5 * temp_norm * signals["humidity"].std()
        
        # PM2.5 - PM10 positive correlation
        if "pm25" in signals and "pm10" in signals:
            pm25_norm = (signals["pm25"] - signals["pm25"].mean()) / (signals["pm25"].std() + 1e-8)
            signals["pm10"] += strength * 0.7 * pm25_norm * signals["pm10"].std()
        
        # Air Quality correlates with PM2.5
        if "air_quality" in signals and "pm25" in signals:
            pm25_norm = (signals["pm25"] - signals["pm25"].mean()) / (signals["pm25"].std() + 1e-8)
            signals["air_quality"] += strength * 0.6 * pm25_norm * signals["air_quality"].std()
        
        # Noise correlates with production activity
        if "noise" in signals and "temperature" in signals:
            # Higher temp = more production = more noise
            temp_norm = (signals["temperature"] - signals["temperature"].mean()) / (signals["temperature"].std() + 1e-8)
            signals["noise"] += strength * 0.3 * temp_norm * signals["noise"].std()
        
        return signals
    
    def _add_anomalies(
        self, 
        signals: Dict[str, np.ndarray], 
        zone_id: str
    ) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
        """Inject anomalies and return labels."""
        n = len(self.context.timestamps)
        anomaly_labels = {param: np.zeros(n, dtype=bool) for param in signals.keys()}
        
        n_anomalies = int(n * self.config.anomaly_ratio)
        
        # Generate anomaly events (affecting multiple parameters)
        for _ in range(n_anomalies // 3):  # Each event affects ~3 parameters
            center = self.rng.integers(100, n - 100)
            duration = self.rng.integers(1, 12)  # 1-12 samples (10-120 min)
            
            # Choose anomaly type
            anomaly_type = self.rng.choice([
                "spike", "drift", "drop", "stuck", "noise_burst"
            ])
            
            # Choose affected parameters (correlated groups)
            param_groups = [
                ["temperature", "humidity"],
                ["pm25", "pm10", "air_quality"],
                ["noise"],
                ["voltage"],
            ]
            group = self.rng.choice(param_groups)
            
            for param in group:
                if param not in signals:
                    continue
                    
                start = max(0, center - duration // 2)
                end = min(n, center + duration // 2)
                
                if anomaly_type == "spike":
                    magnitude = self.rng.uniform(3, 6) * signals[param].std()
                    signals[param][start:end] += magnitude * np.exp(-0.5 * ((np.arange(end-start) - duration//2) / (duration/4))**2)
                    
                elif anomaly_type == "drift":
                    drift_rate = self.rng.uniform(0.5, 2) * signals[param].std()
                    signals[param][start:end] += drift_rate * np.linspace(0, 1, end-start)
                    
                elif anomaly_type == "drop":
                    magnitude = self.rng.uniform(2, 4) * signals[param].std()
                    signals[param][start:end] -= magnitude
                    
                elif anomaly_type == "stuck":
                    # Sensor stuck at constant value
                    stuck_value = signals[param][start]
                    signals[param][start:end] = stuck_value
                    
                elif anomaly_type == "noise_burst":
                    noise = self.rng.normal(0, 5 * signals[param].std(), end-start)
                    signals[param][start:end] += noise
                
                # Clip to valid range
                min_val, max_val = PARAMETER_RANGES[param]
                signals[param] = np.clip(signals[param], min_val, max_val)
                
                # Mark as anomaly
                anomaly_labels[param][start:end] = True
        
        return signals, anomaly_labels
    
    def _build_features(
        self, 
        signals: Dict[str, np.ndarray], 
        index: int, 
        target_param: str
    ) -> Dict[str, float]:
        """Build feature vector for a sample."""
        features = {}
        
        # Current values for all parameters
        for param, signal in signals.items():
            features[f"value_{param}"] = float(signal[index])
        
        # Rolling statistics for target parameter (last 6 samples = 1 hour)
        window = min(6, index + 1)
        target_signal = signals[target_param]
        
        if window > 1:
            recent = target_signal[index - window + 1:index + 1]
            features[f"{target_param}_mean_1h"] = float(recent.mean())
            features[f"{target_param}_std_1h"] = float(recent.std())
            features[f"{target_param}_min_1h"] = float(recent.min())
            features[f"{target_param}_max_1h"] = float(recent.max())
            features[f"{target_param}_trend_1h"] = float(recent[-1] - recent[0]) if len(recent) > 1 else 0.0
        
        # Time features
        features["hour_of_day"] = float(self.context.hour_of_day[index])
        features["day_of_week"] = float(self.context.day_of_week[index])
        features["is_weekend"] = float(self.context.is_weekend[index])
        
        # Cyclical encoding
        features["hour_sin"] = float(np.sin(2 * np.pi * self.context.hour_of_day[index] / 24))
        features["hour_cos"] = float(np.cos(2 * np.pi * self.context.hour_of_day[index] / 24))
        features["doy_sin"] = float(np.sin(2 * np.pi * self.context.day_of_year[index] / 365))
        features["doy_cos"] = float(np.cos(2 * np.pi * self.context.day_of_year[index] / 365))
        
        # Threshold proximity
        thresholds = DEFAULT_THRESHOLDS.get(target_param, {})
        current = signals[target_param][index]
        
        if "warning_max" in thresholds:
            features["proximity_warning_max"] = float(
                (current - thresholds["warning_max"]) / (thresholds.get("critical_max", thresholds["warning_max"]) - thresholds["warning_max"])
            )
        if "warning_min" in thresholds:
            features["proximity_warning_min"] = float(
                (thresholds["warning_min"] - current) / (thresholds["warning_min"] - thresholds.get("critical_min", thresholds["warning_min"]))
            )
        
        # Cross-parameter features
        for param in ["temperature", "humidity", "pm25", "pm10"]:
            if param != target_param and param in signals:
                features[f"cross_{param}"] = float(signals[param][index])
        
        return features


def generate_and_save_synthetic_data(output_path: str = "/app/data/synthetic_training_data.parquet") -> None:
    """Generate synthetic data and save to Parquet."""
    generator = SyntheticDataGenerator()
    samples = generator.generate_all()
    
    # Convert to DataFrame
    data = []
    for s in samples:
        row = {
            "zone_id": s.zone_id,
            "parameter": s.parameter,
            "timestamp": s.timestamp,
            "label": s.label,
            "is_synthetic": s.is_synthetic,
            **s.features,
        }
        data.append(row)
    
    df = pd.DataFrame(data)
    df.to_parquet(output_path, index=False)
    
    logger.info("synthetic_data_saved", path=output_path, rows=len(df))


if __name__ == "__main__":
    generate_and_save_synthetic_data()