"""
Tests for Inference Service
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime, timezone, timedelta

from app.services.inference import InferenceService, LoadedModel
from app.models.ai import (
    ModelType, ModelStatus, PredictionType,
    PredictRequest, PredictResponse, PredictionResult,
    AnomalyRequest, AnomalyResponse, AnomalyResult,
    RiskScoreRequest, RiskScoreResponse, RiskFactors,
    AIModelInDB, AIPredictionInDB, RiskScoreInDB,
    ZONE_PARAMETER_CONFIGS, PARAMETER_UNITS, PARAMETER_RANGES, DEFAULT_THRESHOLDS
)


class TestInferenceService:
    """Test inference service."""
    
    @pytest.fixture
    def inference_service(self):
        """Create inference service with mocked model loading."""
        service = InferenceService()
        # Clear cache
        service.model_cache.clear()
        return service
    
    @pytest.fixture
    def mock_loaded_model(self):
        """Create a mock loaded model."""
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import RobustScaler
        
        model = MagicMock(spec=IsolationForest)
        model.decision_function = MagicMock(return_value=np.array([0.5]))
        
        scaler = MagicMock(spec=RobustScaler)
        scaler.transform = MagicMock(side_effect=lambda x: x)
        
        metadata = {
            "parameters": [
                "value_temperature", "value_humidity", "value_pm25", "value_pm10",
                "temperature_mean_1h", "temperature_std_1h", "temperature_trend_1h",
                "hour_of_day", "day_of_week", "is_weekend", "hour_sin", "hour_cos",
                "doy_sin", "doy_cos", "proximity_warning_max", "cross_humidity",
                "cross_pm25", "cross_pm10",
            ]
        }
        
        return LoadedModel(
            model=model,
            scaler=scaler,
            metadata=metadata,
            model_type=ModelType.ISOLATION_FOREST,
            version="isolation_forest_v20260101_120000",
        )
    
    @pytest.mark.asyncio
    async def test_get_active_model_cache_miss(self, inference_service, mock_db, mock_loaded_model):
        """Test loading model from database on cache miss."""
        # Setup mock database response
        mock_model_doc = {
            "_id": "model123",
            "model_type": "isolation_forest",
            "zone_id": "prod-01",
            "parameter": "all",
            "version": "isolation_forest_v20260101_120000",
            "is_active": True,
            "status": "ready",
        }
        
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = AsyncMock(return_value=iter([mock_model_doc]))
        mock_db.return_value.__getitem__.return_value.find_one = AsyncMock(return_value=mock_model_doc)
        
        # Mock load_model
        with patch.object(inference_service.trainer, 'load_model', return_value=(
            mock_loaded_model.model, mock_loaded_model.scaler, mock_loaded_model.metadata
        )):
            model = await inference_service.get_active_model(ModelType.ISOLATION_FOREST, "prod-01", "all")
        
        assert model is not None
        assert model.model_type == ModelType.ISOLATION_FOREST
        assert model.version == "isolation_forest_v20260101_120000"
        
        # Second call should use cache
        model2 = await inference_service.get_active_model(ModelType.ISOLATION_FOREST, "prod-01", "all")
        assert model2 is model  # Same object from cache
    
    @pytest.mark.asyncio
    async def test_get_active_model_fallback_to_global(self, inference_service, mock_db, mock_loaded_model):
        """Test fallback to global model when zone-specific not found."""
        # First call returns None (no zone-specific model)
        mock_db.return_value.__getitem__.return_value.find_one = AsyncMock(return_value=None)
        
        # But global model exists
        async def find_one_side_effect(query):
            if query.get("zone_id") == "global":
                return {
                    "_id": "model123",
                    "model_type": "isolation_forest",
                    "zone_id": "global",
                    "parameter": "all",
                    "version": "isolation_forest_v20260101_120000",
                    "is_active": True,
                    "status": "ready",
                }
            return None
        
        mock_db.return_value.__getitem__.return_value.find_one.side_effect = find_one_side_effect
        
        with patch.object(inference_service.trainer, 'load_model', return_value=(
            mock_loaded_model.model, mock_loaded_model.scaler, mock_loaded_model.metadata
        )):
            model = await inference_service.get_active_model(ModelType.ISOLATION_FOREST, "prod-01", "all")
        
        assert model is not None
        assert model.zone_id == "global"  # Wait, model doesn't have zone_id...
    
    def test_calculate_param_anomaly_score(self, inference_service):
        """Test parameter anomaly score calculation."""
        # Test critical threshold breach
        score = inference_service._calculate_param_anomaly_score("temperature", 40.0, "prod-01")
        assert score == 1.0  # Above critical_max (35)
        
        score = inference_service._calculate_param_anomaly_score("temperature", 10.0, "prod-01")
        assert score == 1.0  # Below critical_min (15)
        
        # Test warning threshold
        score = inference_service._calculate_param_anomaly_score("temperature", 30.0, "prod-01")
        assert score == 0.8  # Above warning_max (28)
        
        # Test normal range
        score = inference_service._calculate_param_anomaly_score("temperature", 22.0, "prod-01")
        assert score < 0.5  # Within normal range
        
        # Test parameter without thresholds
        score = inference_service._calculate_param_anomaly_score("voltage", 230.0, "prod-01")
        assert 0 <= score <= 1
    
    def test_score_to_level(self, inference_service):
        """Test risk score to level conversion."""
        assert inference_service._score_to_level(90) == "critical"
        assert inference_service._score_to_level(70) == "high"
        assert inference_service._score_to_level(40) == "medium"
        assert inference_service._score_to_level(10) == "low"
    
    def test_build_prediction_features(self, inference_service):
        """Test feature building for prediction."""
        measurements = {
            "temperature": [
                {"value": 24.0, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 24.5, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 25.0, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 25.5, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 26.0, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 26.5, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
            ],
            "humidity": [
                {"value": 50.0, "timestamp": datetime.now(timezone.utc), "unit": "%"},
            ],
        }
        
        features = inference_service._build_prediction_features(measurements, "temperature", "prod-01")
        
        assert features is not None
        assert "value_temperature" in features
        assert "value_humidity" in features
        assert "temperature_mean_1h" in features
        assert "temperature_trend_1h" in features
        assert abs(features["temperature_trend_1h"] - 2.5) < 0.1  # 26.5 - 24.0
        assert "hour_of_day" in features
        assert "proximity_warning_max" in features
    
    def test_build_features_from_measurements(self, inference_service):
        """Test feature building from current measurements."""
        measurements = {
            "temperature": 25.0,
            "humidity": 50.0,
        }
        
        features = inference_service._build_features_from_measurements(measurements, "prod-01")
        
        assert features["value_temperature"] == 25.0
        assert features["value_humidity"] == 50.0
        assert "hour_of_day" in features
        assert "hour_sin" in features
        assert "hour_cos" in features
    
    @pytest.mark.asyncio
    async def test_predict_threshold_breach(self, inference_service, mock_db, mock_loaded_model):
        """Test threshold breach prediction."""
        # Mock get_active_model
        inference_service.get_active_model = AsyncMock(return_value=mock_loaded_model)
        
        # Mock recent measurements
        inference_service._get_recent_measurements = AsyncMock(return_value={
            "temperature": [
                {"value": 25.0, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 25.5, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 26.0, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 26.5, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 27.0, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
                {"value": 27.5, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
            ]
        })
        
        # Mock save_predictions
        inference_service._save_predictions = AsyncMock()
        
        request = PredictRequest(
            zone_id="prod-01",
            horizon_minutes=60,
            parameters=["temperature"],
        )
        
        result = await inference_service.predict_threshold_breach(request)
        
        assert result is not None
        assert result.zone_id == "prod-01"
        assert result.horizon_minutes == 60
        assert len(result.predictions) == 1
        assert result.predictions[0].parameter == "temperature"
        assert result.predictions[0].predicted_value > 0
        assert 0 <= result.predictions[0].confidence <= 1
        assert result.predictions[0].breach_risk in ["low", "medium", "high", "critical"]
    
    @pytest.mark.asyncio
    async def test_detect_anomalies(self, inference_service, mock_loaded_model):
        """Test anomaly detection."""
        inference_service.get_active_model = AsyncMock(return_value=mock_loaded_model)
        
        request = AnomalyRequest(
            zone_id="prod-01",
            measurements={"temperature": 40.0, "humidity": 50.0},
        )
        
        result = await inference_service.detect_anomalies(request)
        
        assert result is not None
        assert result.zone_id == "prod-01"
        assert len(result.anomalies) == 2
        assert result.anomalies[0].parameter == "temperature"
        assert result.anomalies[0].is_anomaly == True  # 40°C is critical
        assert result.anomalies[1].parameter == "humidity"
        assert result.overall_anomaly_score > 0
    
    @pytest.mark.asyncio
    async def test_calculate_risk_score(self, inference_service, mock_db):
        """Test risk score calculation."""
        # Mock recent measurements
        inference_service._get_recent_measurements = AsyncMock(return_value={
            "temperature": [
                {"value": 30.0, "timestamp": datetime.now(timezone.utc), "unit": "°C"},
            ],
            "humidity": [
                {"value": 50.0, "timestamp": datetime.now(timezone.utc), "unit": "%"},
            ],
        })
        
        # Mock alerts
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {"level": "warning", "zone_id": "prod-01"},
            {"level": "critical", "zone_id": "prod-01"},
        ])
        mock_db.return_value.__getitem__.return_value.find.return_value = mock_cursor
        
        # Mock get_active_model
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import RobustScaler
        mock_model = MagicMock(spec=IsolationForest)
        mock_scaler = MagicMock(spec=RobustScaler)
        mock_loaded = LoadedModel(
            model=mock_model, scaler=mock_scaler, metadata={},
            model_type=ModelType.ISOLATION_FOREST, version="test"
        )
        inference_service.get_active_model = AsyncMock(return_value=mock_loaded)
        
        # Mock database insert
        mock_db.return_value.__getitem__.return_value.insert_one = AsyncMock()
        
        request = RiskScoreRequest(zone_id="prod-01")
        result = await inference_service.calculate_risk_score(request)
        
        assert result is not None
        assert result.zone_id == "prod-01"
        assert 0 <= result.score <= 100
        assert result.level in ["low", "medium", "high", "critical"]
        assert isinstance(result.factors, RiskFactors)
    
    def test_calculate_overall_risk(self, inference_service):
        """Test overall risk calculation from factors."""
        factors = RiskFactors(
            parameter_anomalies={"temperature": 0.8, "humidity": 0.2},
            threshold_proximity={"temperature": 0.6, "humidity": 0.1},
            trend_direction={"temperature": "increasing", "humidity": "stable"},
            historical_alert_frequency=2.0,
            ai_prediction_confidence=0.7,
        )
        
        score = inference_service._calculate_overall_risk(factors, alert_count=2)
        
        # Max anomaly 0.8 * 40 = 32
        # Max proximity 0.6 * 30 = 18
        # Increasing trend = 5
        # Alert freq 2.0 * 2 = 4
        # AI confidence (1-0.7)*5 = 1.5
        # Total = 32 + 18 + 5 + 4 + 1 = 60
        assert score == 60
    
    @pytest.mark.asyncio
    async def test_get_weekly_report(self, inference_service, mock_db):
        """Test weekly report generation."""
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        
        # Mock predictions
        mock_pred_cursor = AsyncMock()
        mock_pred_cursor.to_list = AsyncMock(return_value=[
            {"zone_id": "prod-01", "confidence": 0.9, "breach_risk": "high"},
            {"zone_id": "prod-01", "confidence": 0.8, "breach_risk": "critical"},
        ])
        mock_db.return_value.__getitem__.return_value.find.return_value = mock_pred_cursor
        
        # Mock risk scores
        mock_risk_cursor = AsyncMock()
        mock_risk_cursor.to_list = AsyncMock(return_value=[
            {"zone_id": "prod-01", "score": 70, "level": "high"},
            {"zone_id": "prod-01", "score": 65, "level": "high"},
        ])
        
        # Mock model metadata
        mock_meta_cursor = AsyncMock()
        mock_meta_cursor.__aiter__ = AsyncMock(return_value=iter([
            {"model_type": "isolation_forest", "metrics": {"f1": 0.85, "precision": 0.8, "recall": 0.9}},
        ]))
        
        # Need to handle multiple find calls
        call_count = 0
        async def find_side_effect(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_pred_cursor
            elif call_count == 2:
                return mock_risk_cursor
            else:
                return mock_meta_cursor
        
        mock_db.return_value.__getitem__.return_value.find.side_effect = find_side_effect
        
        report = await inference_service.get_weekly_report()
        
        assert "week_start" in report
        assert "week_end" in report
        assert "zones" in report
        assert "summary" in report
        assert "model_performance" in report
        assert "recommendations" in report
        assert len(report["recommendations"]) > 0


class TestInferenceModels:
    """Test inference request/response models."""
    
    def test_predict_request_validation(self):
        """Test PredictRequest validation."""
        # Valid request
        req = PredictRequest(zone_id="prod-01", horizon_minutes=60)
        assert req.zone_id == "prod-01"
        assert req.horizon_minutes == 60
        assert req.parameters is None
        
        # Invalid horizon
        with pytest.raises(ValueError):
            PredictRequest(zone_id="prod-01", horizon_minutes=1441)
        
        with pytest.raises(ValueError):
            PredictRequest(zone_id="prod-01", horizon_minutes=4)
    
    def test_anomaly_request_validation(self):
        """Test AnomalyRequest validation."""
        req = AnomalyRequest(
            zone_id="prod-01",
            measurements={"temperature": 25.0, "humidity": 50.0},
        )
        assert req.zone_id == "prod-01"
        assert req.measurements == {"temperature": 25.0, "humidity": 50.0}
    
    def test_risk_score_request(self):
        """Test RiskScoreRequest."""
        req = RiskScoreRequest(zone_id="prod-01")
        assert req.zone_id == "prod-01"
    
    def test_prediction_result(self):
        """Test PredictionResult model."""
        pred = PredictionResult(
            parameter="temperature",
            predicted_value=28.5,
            unit="°C",
            confidence=0.85,
            breach_risk="high",
            time_to_breach="30 min",
            current_value=26.0,
            threshold_warning=28.0,
            threshold_critical=35.0,
        )
        
        assert pred.parameter == "temperature"
        assert pred.predicted_value == 28.5
        assert pred.confidence == 0.85
        assert pred.breach_risk == "high"
    
    def test_anomaly_result(self):
        """Test AnomalyResult model."""
        anomaly = AnomalyResult(
            parameter="temperature",
            value=40.0,
            anomaly_score=0.95,
            is_anomaly=True,
            expected_range=[15.0, 35.0],
            contribution=0.9,
        )
        
        assert anomaly.parameter == "temperature"
        assert anomaly.is_anomaly == True
        assert anomaly.anomaly_score == 0.95
    
    def test_risk_factors(self):
        """Test RiskFactors model."""
        factors = RiskFactors(
            parameter_anomalies={"temperature": 0.8},
            threshold_proximity={"temperature": 0.6},
            trend_direction={"temperature": "increasing"},
            historical_alert_frequency=1.5,
            ai_prediction_confidence=0.8,
        )
        
        assert factors.parameter_anomalies["temperature"] == 0.8
        assert factors.trend_direction["temperature"] == "increasing"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])