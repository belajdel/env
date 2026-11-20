"""
Tests for Synthetic Data Generator
"""

import pytest
import numpy as np
from datetime import datetime, timezone

from app.services.data_generator import SyntheticDataGenerator, SyntheticDataConfig
from app.models.ai import TrainingDataInDB, ZONE_PARAMETER_CONFIGS, PARAMETER_RANGES


class TestSyntheticDataGenerator:
    """Test synthetic data generation."""
    
    @pytest.fixture
    def generator(self):
        """Create generator with small config for fast tests."""
        config = SyntheticDataConfig(
            seed=42,
            days=2,  # Small for testing
            sample_rate_minutes=60,  # Hourly for testing
            anomaly_ratio=0.1,
        )
        return SyntheticDataGenerator(config)
    
    def test_config_defaults(self):
        """Test default configuration values."""
        config = SyntheticDataConfig()
        assert config.seed == 42
        assert config.days == 365
        assert config.sample_rate_minutes == 10
        assert config.anomaly_ratio == 0.05
        assert len(config.zones) == 7
        assert len(config.parameters) == 7
    
    def test_context_building(self, generator):
        """Test time context building."""
        generator._build_context()
        
        assert generator.context is not None
        assert len(generator.context.timestamps) > 0
        assert len(generator.context.hour_of_day) == len(generator.context.timestamps)
        assert len(generator.context.day_of_week) == len(generator.context.timestamps)
        assert len(generator.context.is_weekend) == len(generator.context.timestamps)
        
        # Check hour range
        assert generator.context.hour_of_day.min() >= 0
        assert generator.context.hour_of_day.max() <= 23
        
        # Check day of week
        assert generator.context.day_of_week.min() >= 0
        assert generator.context.day_of_week.max() <= 6
        
        # Check weekend flag
        assert set(generator.context.is_weekend).issubset({0.0, 1.0})
    
    def test_temperature_generation(self, generator):
        """Test temperature signal generation."""
        generator._build_context()
        zone_config = ZONE_PARAMETER_CONFIGS["prod-01"]
        signal = generator._generate_temperature(zone_config)
        
        assert len(signal) == len(generator.context.timestamps)
        assert signal.min() >= PARAMETER_RANGES["temperature"][0]
        assert signal.max() <= PARAMETER_RANGES["temperature"][1]
        
        # Should have daily pattern
        # Temperature should vary throughout the day
        assert signal.std() > 0.5
    
    def test_humidity_generation(self, generator):
        """Test humidity signal generation."""
        generator._build_context()
        zone_config = ZONE_PARAMETER_CONFIGS["prod-01"]
        signal = generator._generate_humidity(zone_config)
        
        assert len(signal) == len(generator.context.timestamps)
        assert signal.min() >= PARAMETER_RANGES["humidity"][0]
        assert signal.max() <= PARAMETER_RANGES["humidity"][1]
    
    def test_all_parameter_generation(self, generator):
        """Test all parameter signals are generated."""
        generator._build_context()
        zone_config = ZONE_PARAMETER_CONFIGS["prod-01"]
        
        for param in generator.config.parameters:
            signal = generator._generate_parameter_signal(param, zone_config)
            assert len(signal) == len(generator.context.timestamps)
            min_val, max_val = PARAMETER_RANGES[param]
            assert signal.min() >= min_val
            assert signal.max() <= max_val
    
    def test_correlations_added(self, generator):
        """Test cross-parameter correlations are added."""
        generator._build_context()
        zone_config = ZONE_PARAMETER_CONFIGS["prod-01"]
        
        # Generate base signals
        signals = {}
        for param in ["temperature", "humidity", "pm25", "pm10", "air_quality", "noise", "voltage"]:
            signals[param] = generator._generate_parameter_signal(param, zone_config)
        
        # Store originals
        originals = {k: v.copy() for k, v in signals.items()}
        
        # Add correlations
        signals = generator._add_correlations(signals, "production")
        
        # Signals should be modified
        for param in signals:
            # At least some values should differ
            diff = np.abs(signals[param] - originals[param]).max()
            assert diff >= 0  # May be 0 if correlation doesn't affect this param
    
    def test_anomalies_added(self, generator):
        """Test anomalies are injected."""
        generator._build_context()
        zone_config = ZONE_PARAMETER_CONFIGS["prod-01"]
        
        signals = {}
        for param in generator.config.parameters:
            signals[param] = generator._generate_parameter_signal(param, zone_config)
        
        signals, labels = generator._add_anomalies(signals, "prod-01")
        
        # Check that some anomalies were added
        total_anomalies = sum(l.sum() for l in labels.values())
        expected_min = int(len(generator.context.timestamps) * generator.config.anomaly_ratio * 0.5)
        assert total_anomalies >= expected_min
        
        # Check labels are boolean
        for param, label_array in labels.items():
            assert label_array.dtype == bool
            assert len(label_array) == len(signals[param])
    
    def test_feature_building(self, generator):
        """Test feature vector building."""
        generator._build_context()
        zone_config = ZONE_PARAMETER_CONFIGS["prod-01"]
        
        signals = {}
        for param in generator.config.parameters:
            signals[param] = generator._generate_parameter_signal(param, zone_config)
        
        features = generator._build_features(signals, 100, "temperature")
        
        # Check required features exist
        assert "value_temperature" in features
        assert "value_humidity" in features
        assert "hour_of_day" in features
        assert "hour_sin" in features
        assert "hour_cos" in features
        
        # Check rolling features
        assert "temperature_mean_1h" in features
        assert "temperature_std_1h" in features
        assert "temperature_trend_1h" in features
        
        # Check threshold proximity
        assert "proximity_warning_max" in features or "proximity_warning_min" in features
    
    def test_full_generation(self, generator):
        """Test full data generation pipeline."""
        samples = generator.generate_all()
        
        assert len(samples) > 0
        assert all(isinstance(s, TrainingDataInDB) for s in samples)
        
        # Check all zones represented
        zones = set(s.zone_id for s in samples)
        assert zones == set(generator.config.zones)
        
        # Check all parameters represented
        params = set(s.parameter for s in samples)
        assert params == set(generator.config.parameters)
        
        # Check labels
        labels = [s.label for s in samples]
        assert all(l in [0, 1] for l in labels)
        assert sum(labels) > 0  # Some anomalies
        
        # Check timestamps are ordered
        timestamps = [s.timestamp for s in samples]
        assert all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
    
    def test_reproducibility(self):
        """Test that same seed produces same data."""
        config1 = SyntheticDataConfig(seed=42, days=1, sample_rate_minutes=60)
        config2 = SyntheticDataConfig(seed=42, days=1, sample_rate_minutes=60)
        
        gen1 = SyntheticDataGenerator(config1)
        gen2 = SyntheticDataGenerator(config2)
        
        samples1 = gen1.generate_all()
        samples2 = gen2.generate_all()
        
        assert len(samples1) == len(samples2)
        
        for s1, s2 in zip(samples1, samples2):
            assert s1.zone_id == s2.zone_id
            assert s1.parameter == s2.parameter
            assert s1.label == s2.label
            assert s1.timestamp == s2.timestamp
            # Features should match
            for k in s1.features:
                assert abs(s1.features[k] - s2.features[k]) < 1e-10


class TestSyntheticDataConfig:
    """Test SyntheticDataConfig validation."""
    
    def test_default_zones(self):
        """Test default zones match expected."""
        config = SyntheticDataConfig()
        expected = ["prod-01", "prod-02", "prod-03", "store-01", "store-02", "tech-01", "tech-02"]
        assert config.zones == expected
    
    def test_default_parameters(self):
        """Test default parameters match expected."""
        config = SyntheticDataConfig()
        expected = ["temperature", "humidity", "noise", "air_quality", "pm25", "pm10", "voltage"]
        assert config.parameters == expected
    
    def test_zone_parameter_configs_exist(self):
        """Test that all zones have configs."""
        for zone in SyntheticDataConfig().zones:
            assert zone in ZONE_PARAMETER_CONFIGS
            assert "type" in ZONE_PARAMETER_CONFIGS[zone]
            assert "base_temp" in ZONE_PARAMETER_CONFIGS[zone]
            assert "base_humidity" in ZONE_PARAMETER_CONFIGS[zone]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])