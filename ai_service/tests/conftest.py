"""
Pytest Configuration for AI Service Tests
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import Settings
from app.models.ai import (
    ModelType, ModelStatus, DataSource, PredictionType,
    AIModelInDB, AIPredictionInDB, RiskScoreInDB,
    TrainingDataInDB, SyntheticDataConfig,
    ZONE_PARAMETER_CONFIGS, PARAMETER_RANGES, DEFAULT_THRESHOLDS
)


# Test settings
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Test settings."""
    return Settings(
        MONGO_URI="mongodb://localhost:27017",
        MONGO_DB="env_monitoring_test",
        MODEL_DIR="/tmp/test_models",
        SYNTHETIC_DATA_SEED=42,
        SYNTHETIC_DAYS=30,
        SYNTHETIC_SAMPLE_RATE_MINUTES=10,
        DEBUG=True,
        LOG_LEVEL="DEBUG",
    )


# Event loop
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Mock database
@pytest.fixture
def mock_db():
    """Mock database for unit tests."""
    db = AsyncMock()
    db.command = AsyncMock(return_value={"ok": 1})
    return db


# Sample training data
@pytest.fixture
def sample_training_data() -> list:
    """Sample training data for testing."""
    return [
        TrainingDataInDB(
            zone_id="prod-01",
            parameter="temperature",
            features={
                "value_temperature": 25.0,
                "value_humidity": 50.0,
                "value_pm25": 12.0,
                "value_pm10": 25.0,
                "temperature_mean_1h": 24.5,
                "temperature_std_1h": 0.5,
                "temperature_trend_1h": 0.1,
                "hour_of_day": 12.0,
                "day_of_week": 2.0,
                "is_weekend": 0.0,
                "hour_sin": 0.0,
                "hour_cos": -1.0,
                "doy_sin": 0.5,
                "doy_cos": 0.866,
            },
            label=0,
            timestamp=datetime.now(timezone.utc),
            is_synthetic=True,
        ),
        TrainingDataInDB(
            zone_id="prod-01",
            parameter="temperature",
            features={
                "value_temperature": 38.0,
                "value_humidity": 45.0,
                "value_pm25": 15.0,
                "value_pm10": 30.0,
                "temperature_mean_1h": 35.0,
                "temperature_std_1h": 2.0,
                "temperature_trend_1h": 1.5,
                "hour_of_day": 14.0,
                "day_of_week": 2.0,
                "is_weekend": 0.0,
                "hour_sin": 0.707,
                "hour_cos": 0.707,
                "doy_sin": 0.5,
                "doy_cos": 0.866,
            },
            label=1,
            timestamp=datetime.now(timezone.utc),
            is_synthetic=True,
        ),
    ]


# Mock model
@pytest.fixture
def mock_isolation_forest():
    """Mock Isolation Forest model."""
    from sklearn.ensemble import IsolationForest
    import numpy as np
    
    model = MagicMock(spec=IsolationForest)
    model.decision_function = MagicMock(return_value=np.array([0.5, -0.5]))
    model.predict = MagicMock(return_value=np.array([1, -1]))
    model.estimators_ = []
    return model


# Mock scaler
@pytest.fixture
def mock_scaler():
    """Mock scaler."""
    from sklearn.preprocessing import RobustScaler
    import numpy as np
    
    scaler = MagicMock(spec=RobustScaler)
    scaler.transform = MagicMock(side_effect=lambda x: x)
    scaler.fit_transform = MagicMock(side_effect=lambda x: x)
    return scaler


# Patch external dependencies
@pytest.fixture(autouse=True)
def patch_external():
    """Patch external services for unit tests."""
    with patch("app.services.model_trainer.get_database") as mock_db, \
         patch("app.services.inference.get_database") as mock_db2, \
         patch("app.api.routes.get_database") as mock_db3, \
         patch("app.core.database.get_database") as mock_db4:
        
        mock_collection = AsyncMock()
        mock_collection.find = AsyncMock(return_value=AsyncMock(__aiter__=AsyncMock(return_value=iter([]))))
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_collection.insert_one = AsyncMock()
        mock_collection.insert_many = AsyncMock()
        mock_collection.update_one = AsyncMock()
        mock_collection.update_many = AsyncMock()
        mock_collection.delete_many = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_collection.to_list = AsyncMock(return_value=[])
        
        mock_db.return_value = MagicMock()
        mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
        mock_db2.return_value = MagicMock()
        mock_db2.return_value.__getitem__ = MagicMock(return_value=mock_collection)
        mock_db3.return_value = MagicMock()
        mock_db3.return_value.__getitem__ = MagicMock(return_value=mock_collection)
        mock_db4.return_value = MagicMock()
        mock_db4.return_value.__getitem__ = MagicMock(return_value=mock_collection)
        
        yield {
            "db": mock_db,
            "collection": mock_collection,
        }