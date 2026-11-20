"""
Tests for Model Trainer
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime, timezone

from app.services.model_trainer import ModelTrainer, TrainingResult
from app.models.ai import ModelType, ModelStatus, DataSource, AIModelInDB, ModelMetadataInDB


class TestModelTrainer:
    """Test model training functionality."""
    
    @pytest.fixture
    def trainer(self):
        """Create trainer with temp directory."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ModelTrainer(model_dir=tmpdir)
    
    @pytest.fixture
    def sample_data(self):
        """Create sample training data."""
        np.random.seed(42)
        n_samples = 1000
        n_features = 20
        
        # Normal data
        X_normal = np.random.randn(n_samples, n_features)
        
        # Anomalous data (shifted)
        X_anomaly = np.random.randn(50, n_features) + 3
        
        X = np.vstack([X_normal, X_anomaly])
        y = np.hstack([np.zeros(n_samples), np.ones(50)])
        
        # Shuffle
        idx = np.random.permutation(len(X))
        X = X[idx]
        y = y[idx]
        
        feature_cols = [f"feature_{i}" for i in range(n_features)]
        df = pd.DataFrame(X, columns=feature_cols)
        df['label'] = y
        
        return X, y, feature_cols, df
    
    def test_prepare_data_mock(self, trainer, mock_db):
        """Test data preparation with mocked database."""
        # Setup mock data
        mock_docs = [
            {
                "zone_id": "prod-01",
                "parameter": "temperature",
                "features": {"feature_1": 1.0, "feature_2": 2.0},
                "label": 0,
                "timestamp": datetime.now(timezone.utc),
                "is_synthetic": True,
            }
            for _ in range(100)
        ]
        
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter(mock_docs))
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        
        mock_db.return_value.__getitem__.return_value.find.return_value = mock_cursor
        
        # Mock count_documents
        mock_db.return_value.__getitem__.return_value.count_documents = AsyncMock(return_value=100)
        
        X, y, feature_cols, df = trainer.prepare_data(zone_id="prod-01", parameter="temperature")
        
        assert X.shape[0] == 100
        assert X.shape[1] == 2
        assert len(feature_cols) == 2
        assert list(feature_cols) == ["feature_1", "feature_2"]
    
    def test_train_isolation_forest(self, trainer, sample_data):
        """Test Isolation Forest training."""
        X, y, feature_cols, df = sample_data
        
        result = trainer.train_isolation_forest(X, y)
        
        assert result.model_type == ModelType.ISOLATION_FOREST
        assert result.model is not None
        assert result.scaler is not None
        assert result.metrics is not None
        assert "precision" in result.metrics
        assert "recall" in result.metrics
        assert "f1" in result.metrics
        assert "roc_auc" in result.metrics
        assert result.training_duration > 0
        assert result.version.startswith("isolation_forest_v")
    
    def test_isolation_forest_metrics(self, trainer, sample_data):
        """Test Isolation Forest produces reasonable metrics."""
        X, y, feature_cols, df = sample_data
        
        result = trainer.train_isolation_forest(X, y)
        
        # With clear separation, metrics should be good
        assert result.metrics["precision"] > 0.5
        assert result.metrics["recall"] > 0.5
        assert result.metrics["f1"] > 0.5
        assert result.metrics["roc_auc"] > 0.7
    
    def test_calculate_metrics(self, trainer):
        """Test metric calculation."""
        y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        y_pred = np.array([0, 0, 0, 1, 0, 1, 1, 1])
        scores = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
        
        metrics = trainer._calculate_metrics(y_true, y_pred, scores)
        
        assert metrics["precision"] == 0.75  # 3 TP / (3 TP + 1 FP)
        assert metrics["recall"] == 0.75  # 3 TP / (3 TP + 1 FN)
        assert metrics["f1"] == 0.75
        assert metrics["roc_auc"] > 0.5
    
    def test_calculate_metrics_edge_cases(self, trainer):
        """Test metric calculation with edge cases."""
        # All zeros
        y_true = np.zeros(10)
        y_pred = np.zeros(10)
        scores = np.zeros(10)
        
        metrics = trainer._calculate_metrics(y_true, y_pred, scores)
        
        assert metrics["precision"] == 0  # zero_division=0
        assert metrics["recall"] == 0
        assert metrics["f1"] == 0
        assert metrics["roc_auc"] == 0.5
    
    def test_generate_version(self, trainer):
        """Test version string generation."""
        version = trainer._generate_version(ModelType.ISOLATION_FOREST)
        
        assert version.startswith("isolation_forest_v")
        assert len(version) > len("isolation_forest_v")
        # Should contain timestamp
        parts = version.split("_v")
        assert len(parts) == 2
        # Timestamp format: YYYYMMDD_HHMMSS
        timestamp = parts[1]
        assert len(timestamp) == 15  # YYYYMMDD_HHMMSS
    
    def test_save_load_isolation_forest(self, trainer, sample_data):
        """Test saving and loading Isolation Forest model."""
        X, y, feature_cols, df = sample_data
        
        result = trainer.train_isolation_forest(X, y)
        model_path = trainer.save_model(result, "prod-01", "temperature")
        
        # Check files exist
        import os
        assert os.path.exists(os.path.join(model_path, "model.joblib"))
        assert os.path.exists(os.path.join(model_path, "scaler.joblib"))
        assert os.path.exists(os.path.join(model_path, "metadata.json"))
        
        # Load model
        loaded_model, loaded_scaler, metadata = trainer.load_model(
            ModelType.ISOLATION_FOREST, "prod-01", "temperature"
        )
        
        assert loaded_model is not None
        assert loaded_scaler is not None
        assert metadata["model_type"] == "isolation_forest"
        assert metadata["version"] == result.version
        assert metadata["zone_id"] == "prod-01"
        assert metadata["parameter"] == "temperature"
    
    @pytest.mark.skipif(True, reason="TensorFlow not available in test environment")
    def test_train_autoencoder(self, trainer, sample_data):
        """Test Autoencoder training (requires TensorFlow)."""
        pass
    
    @pytest.mark.skipif(True, reason="TensorFlow not available in test environment")
    def test_train_lstm(self, trainer, sample_data):
        """Test LSTM training (requires TensorFlow)."""
        pass


class TestModelTrainerIntegration:
    """Integration tests for model training pipeline."""
    
    @pytest.fixture
    def trainer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ModelTrainer(model_dir=tmpdir)
    
    @pytest.mark.asyncio
    async def test_train_all_models_mock(self, trainer, mock_db, sample_data):
        """Test full training pipeline with mocks."""
        X, y, feature_cols, df = sample_data
        
        # Mock prepare_data to return our sample data
        with patch.object(trainer, 'prepare_data', return_value=(X, y, feature_cols, df)):
            # Mock database insert operations
            mock_collection = AsyncMock()
            mock_collection.insert_one = AsyncMock()
            mock_db.return_value.__getitem__.return_value = mock_collection
            
            result = await trainer.train_all_models(
                zone_id="prod-01",
                parameter="temperature",
                data_source=DataSource.SYNTHETIC,
                force=True,
            )
        
        assert result["status"] == "completed"
        assert "results" in result
        assert "isolation_forest" in result["results"]
        assert result["best_model"] == "isolation_forest"
        assert result["best_f1"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])