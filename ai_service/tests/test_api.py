"""
Tests for AI Service API Routes
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from app.main import app


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.core.database.get_database") as mock_db:
            
            mock_db.return_value.command = AsyncMock(return_value={"ok": 1})
            mock_db.return_value.__getitem__.return_value.find_one = AsyncMock(return_value={
                "created_at": datetime.now(timezone.utc),
            })
            mock_db.return_value.__getitem__.return_value.find = AsyncMock(
                return_value=AsyncMock(__aiter__=AsyncMock(return_value=iter([])))
            )
            
            with TestClient(app) as client:
                yield client
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Environmental Monitoring AI Service"
        assert "version" in data
        assert "models_loaded" in data
        assert "database" in data


class TestPredictEndpoint:
    """Test prediction endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.api.routes.get_inference_service") as mock_inference:
            
            mock_service = AsyncMock()
            mock_service.predict_threshold_breach = AsyncMock(return_value=MagicMock(
                zone_id="prod-01",
                horizon_minutes=60,
                predictions=[
                    MagicMock(
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
                ],
                model_type="isolation_forest",
                model_version="isolation_forest_v20260101_120000",
            ))
            mock_inference.return_value = mock_service
            
            with TestClient(app) as client:
                yield client
    
    def test_predict_success(self, client):
        """Test successful prediction."""
        response = client.post(
            "/api/v1/predict",
            json={"zone_id": "prod-01", "horizon_minutes": 60}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["zone_id"] == "prod-01"
        assert data["horizon_minutes"] == 60
        assert len(data["predictions"]) == 1
        assert data["predictions"][0]["parameter"] == "temperature"
    
    def test_predict_invalid_zone(self, client):
        """Test prediction with invalid zone."""
        response = client.post(
            "/api/v1/predict",
            json={"zone_id": "invalid-zone", "horizon_minutes": 60}
        )
        
        # Should still work but return 503 if no model
        assert response.status_code in [200, 503]
    
    def test_predict_invalid_horizon(self, client):
        """Test prediction with invalid horizon."""
        response = client.post(
            "/api/v1/predict",
            json={"zone_id": "prod-01", "horizon_minutes": 2000}
        )
        
        assert response.status_code == 422  # Validation error


class TestAnomalyEndpoint:
    """Test anomaly detection endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.api.routes.get_inference_service") as mock_inference:
            
            mock_service = AsyncMock()
            mock_service.detect_anomalies = AsyncMock(return_value=MagicMock(
                zone_id="prod-01",
                timestamp=datetime.now(timezone.utc),
                anomalies=[
                    MagicMock(
                        parameter="temperature",
                        value=40.0,
                        anomaly_score=0.95,
                        is_anomaly=True,
                        expected_range=[15.0, 35.0],
                        contribution=0.9,
                    )
                ],
                overall_anomaly_score=0.95,
                model_type="isolation_forest",
                model_version="test",
            ))
            mock_inference.return_value = mock_service
            
            with TestClient(app) as client:
                yield client
    
    def test_anomaly_detection(self, client):
        """Test anomaly detection."""
        response = client.post(
            "/api/v1/anomaly",
            json={
                "zone_id": "prod-01",
                "measurements": {"temperature": 40.0, "humidity": 50.0}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["zone_id"] == "prod-01"
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["is_anomaly"] == True


class TestRiskEndpoint:
    """Test risk scoring endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.api.routes.get_inference_service") as mock_inference:
            
            mock_service = AsyncMock()
            mock_service.calculate_risk_score = AsyncMock(return_value=MagicMock(
                zone_id="prod-01",
                score=75,
                level="high",
                factors=MagicMock(
                    parameter_anomalies={"temperature": 0.8},
                    threshold_proximity={"temperature": 0.6},
                    trend_direction={"temperature": "increasing"},
                    historical_alert_frequency=2.0,
                    ai_prediction_confidence=0.8,
                ),
                model_type="isolation_forest",
                model_version="test",
            ))
            mock_inference.return_value = mock_service
            
            with TestClient(app) as client:
                yield client
    
    def test_risk_score(self, client):
        """Test risk score retrieval."""
        response = client.get("/api/v1/risk/prod-01")
        
        assert response.status_code == 200
        data = response.json()
        assert data["zone_id"] == "prod-01"
        assert data["score"] == 75
        assert data["level"] == "high"


class TestRetrainEndpoint:
    """Test model retraining endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"):
            with TestClient(app) as client:
                yield client
    
    def test_retrain_triggered(self, client):
        """Test retraining is triggered in background."""
        response = client.post(
            "/api/v1/retrain",
            json={"model_type": "isolation_forest", "force": True}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "training"
        assert "Retraining started" in data["message"]


class TestModelsEndpoint:
    """Test model listing endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.core.database.get_database") as mock_db:
            
            mock_collection = AsyncMock()
            mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    {
                        "_id": "model123",
                        "model_type": "isolation_forest",
                        "zone_id": "prod-01",
                        "parameter": "all",
                        "version": "test",
                        "is_active": True,
                        "status": "ready",
                        "metrics": {"f1": 0.85},
                        "created_at": datetime.now(timezone.utc),
                    }
                ]))
            )
            mock_db.return_value.__getitem__.return_value = mock_collection
            
            with TestClient(app) as client:
                yield client
    
    def test_list_models(self, client):
        """Test model listing."""
        response = client.get("/api/v1/models")
        
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) >= 0


class TestWeeklyReportEndpoint:
    """Test weekly report endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.api.routes.get_inference_service") as mock_inference:
            
            mock_service = AsyncMock()
            mock_service.get_weekly_report = AsyncMock(return_value={
                "week_start": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
                "week_end": datetime.now(timezone.utc).isoformat(),
                "zones": {
                    "prod-01": {
                        "predictions_count": 100,
                        "avg_confidence": 0.85,
                        "breach_risk_distribution": {"low": 50, "medium": 30, "high": 15, "critical": 5},
                        "avg_risk_score": 45,
                        "max_risk_score": 80,
                    }
                },
                "summary": {
                    "total_predictions": 100,
                    "total_zones_monitored": 7,
                    "critical_alerts_predicted": 5,
                    "zones_at_high_risk": 2,
                },
                "model_performance": {
                    "isolation_forest": {"f1": 0.85, "precision": 0.8, "recall": 0.9}
                },
                "recommendations": ["All zones operating normally"],
            })
            mock_inference.return_value = mock_service
            
            with TestClient(app) as client:
                yield client
    
    def test_weekly_report(self, client):
        """Test weekly report retrieval."""
        response = client.get("/api/v1/report/weekly")
        
        assert response.status_code == 200
        data = response.json()
        assert "week_start" in data
        assert "week_end" in data
        assert "zones" in data
        assert "summary" in data
        assert "recommendations" in data


class TestDataEndpoints:
    """Test data management endpoints."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"):
            with TestClient(app) as client:
                yield client
    
    def test_generate_synthetic_data(self, client):
        """Test synthetic data generation trigger."""
        response = client.post("/api/v1/data/generate-synthetic?days=30")
        
        assert response.status_code == 200
        data = response.json()
        assert "started in background" in data["message"].lower()
    
    def test_clear_training_data(self, client):
        """Test clearing training data."""
        with patch("app.core.database.get_database") as mock_db:
            mock_collection = AsyncMock()
            mock_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=100))
            mock_db.return_value.__getitem__.return_value = mock_collection
            
            response = client.post("/api/v1/data/clear-training")
            
            assert response.status_code == 200
            data = response.json()
            assert "deleted_count" in data


class TestComparisonEndpoint:
    """Test model comparison endpoint."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.core.database.get_database") as mock_db:
            
            mock_collection = AsyncMock()
            mock_collection.find.return_value.sort.return_value = AsyncMock(
                __aiter__=AsyncMock(return_value=iter([
                    {
                        "model_type": "isolation_forest",
                        "version": "v1",
                        "metrics": {"f1": 0.85, "precision": 0.8, "recall": 0.9},
                        "training_duration_seconds": 30,
                        "data_stats": {"n_samples": 1000},
                        "created_at": datetime.now(timezone.utc),
                    }
                ]))
            )
            mock_db.return_value.__getitem__.return_value = mock_collection
            
            with TestClient(app) as client:
                yield client
    
    def test_compare_models(self, client):
        """Test model comparison."""
        response = client.get("/api/v1/compare")
        
        assert response.status_code == 200
        data = response.json()
        assert "comparison" in data
        assert "recommended_model" in data
        assert "best_f1" in data


# Import datetime for tests
from datetime import datetime, timezone, timedelta