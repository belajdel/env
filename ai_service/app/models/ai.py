"""
AI Service Models
Pydantic models for AI service API and data structures
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId
from typing import Annotated

# Custom type for ObjectId
PyObjectId = Annotated[str, Field(default_factory=lambda: str(ObjectId()))]


class ModelType(str, Enum):
    """Supported ML model types."""
    ISOLATION_FOREST = "isolation_forest"
    AUTOENCODER = "autoencoder"
    LSTM = "lstm"
    ENSEMBLE = "ensemble"


class PredictionType(str, Enum):
    """Types of predictions."""
    THRESHOLD_BREACH = "threshold_breach"
    ANOMALY_SCORE = "anomaly_score"
    TREND = "trend"
    RISK_LEVEL = "risk_level"


class ModelStatus(str, Enum):
    """Model training status."""
    TRAINING = "training"
    READY = "ready"
    FAILED = "failed"
    DEPRECATED = "deprecated"


class DataSource(str, Enum):
    """Data source for training."""
    REAL = "real"
    SYNTHETIC = "synthetic"
    MIXED = "mixed"


# ============================================
# Request/Response Models
# ============================================

class PredictRequest(BaseModel):
    """Request for threshold breach predictions."""
    zone_id: str = Field(..., description="Zone ID")
    horizon_minutes: int = Field(default=60, ge=5, le=1440, description="Prediction horizon in minutes")
    parameters: Optional[List[str]] = Field(default=None, description="Parameters to predict (None = all)")


class PredictionResult(BaseModel):
    """Single prediction result."""
    parameter: str = Field(..., description="Parameter name")
    predicted_value: float = Field(..., description="Predicted value")
    unit: str = Field(..., description="Unit of measurement")
    confidence: float = Field(..., ge=0, le=1, description="Prediction confidence (0-1)")
    breach_risk: Literal["low", "medium", "high", "critical"] = Field(..., description="Breach risk level")
    time_to_breach: Optional[str] = Field(default=None, description="Estimated time to threshold breach")
    current_value: Optional[float] = Field(default=None, description="Current measured value")
    threshold_warning: Optional[float] = Field(default=None, description="Warning threshold")
    threshold_critical: Optional[float] = Field(default=None, description="Critical threshold")


class PredictResponse(BaseModel):
    """Response for predictions."""
    zone_id: str
    horizon_minutes: int
    predictions: List[PredictionResult]
    model_type: ModelType
    model_version: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class AnomalyRequest(BaseModel):
    """Request for anomaly detection."""
    zone_id: str = Field(..., description="Zone ID")
    measurements: Dict[str, float] = Field(..., description="Parameter -> value mapping")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)


class AnomalyResult(BaseModel):
    """Anomaly detection result."""
    parameter: str
    value: float
    anomaly_score: float = Field(..., ge=0, le=1, description="Anomaly score (0-1)")
    is_anomaly: bool
    expected_range: Optional[List[float]] = Field(default=None, description="[min, max] expected range")
    contribution: Optional[float] = Field(default=None, description="Feature contribution to anomaly")


class AnomalyResponse(BaseModel):
    """Response for anomaly detection."""
    zone_id: str
    timestamp: datetime
    anomalies: List[AnomalyResult]
    overall_anomaly_score: float
    model_type: ModelType
    model_version: str


class RiskScoreRequest(BaseModel):
    """Request for risk score."""
    zone_id: str


class RiskFactors(BaseModel):
    """Risk score contributing factors."""
    parameter_anomalies: Dict[str, float] = Field(default_factory=dict, description="Parameter -> anomaly score")
    threshold_proximity: Dict[str, float] = Field(default_factory=dict, description="Parameter -> proximity to threshold (0-1)")
    trend_direction: Dict[str, Literal["increasing", "decreasing", "stable"]] = Field(default_factory=dict)
    historical_alert_frequency: Optional[float] = Field(default=None, description="Alerts per hour in last 24h")
    ai_prediction_confidence: Optional[float] = Field(default=None, description="Average prediction confidence")


class RiskScoreResponse(BaseModel):
    """Response for risk score."""
    zone_id: str
    score: int = Field(..., ge=0, le=100, description="Risk score 0-100")
    level: Literal["low", "medium", "high", "critical"]
    factors: RiskFactors
    model_type: ModelType
    model_version: str
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


class RetrainRequest(BaseModel):
    """Request for model retraining."""
    model_type: Optional[ModelType] = Field(default=None, description="Specific model to retrain (None = all)")
    force: bool = Field(default=False, description="Force retrain even if recent")
    data_source: DataSource = Field(default=DataSource.MIXED, description="Data source for training")


class RetrainResponse(BaseModel):
    """Response for retraining."""
    model_type: ModelType
    status: ModelStatus
    message: str
    training_samples: int
    metrics: Dict[str, float]
    model_version: str
    started_at: datetime
    completed_at: Optional[datetime] = None


class WeeklyReportResponse(BaseModel):
    """Weekly AI analysis report."""
    week_start: datetime
    week_end: datetime
    zones: Dict[str, Dict[str, Any]]
    summary: Dict[str, Any]
    model_performance: Dict[str, Dict[str, float]]
    recommendations: List[str]
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    models_loaded: int
    last_training: Optional[datetime]
    database: str
    mqtt: str


# ============================================
# Database Models
# ============================================

class AIModelInDB(BaseModel):
    """AI Model stored in database."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    model_type: ModelType
    version: str
    status: ModelStatus
    is_active: bool = False
    parameters: List[str] = Field(default_factory=list)
    hyperparameters: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, float] = Field(default_factory=dict)
    training_samples: int = 0
    data_source: DataSource
    model_path: Optional[str] = None
    scaler_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    activated_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None


class AIPredictionInDB(BaseModel):
    """AI Prediction stored in database."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    zone_id: str
    parameter: str
    prediction_type: PredictionType
    horizon_minutes: int
    predicted_value: float
    confidence: float
    breach_risk: str
    time_to_breach: Optional[str]
    current_value: Optional[float]
    model_type: ModelType
    model_version: str
    actual_value: Optional[float] = None  # Filled later for validation
    is_accurate: Optional[bool] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    validated_at: Optional[datetime] = None


class RiskScoreInDB(BaseModel):
    """Risk Score stored in database."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    zone_id: str
    score: int
    level: str
    factors: Dict[str, Any]
    model_type: ModelType
    model_version: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TrainingDataInDB(BaseModel):
    """Training data sample stored in database."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    zone_id: str
    parameter: str
    features: Dict[str, float]
    label: int  # 0 = normal, 1 = anomaly
    timestamp: datetime
    is_synthetic: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ModelMetadataInDB(BaseModel):
    """Model training metadata."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    model_type: ModelType
    version: str
    training_config: Dict[str, Any]
    data_stats: Dict[str, Any]
    metrics: Dict[str, float]
    feature_importance: Optional[Dict[str, float]] = None
    training_duration_seconds: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================
# Synthetic Data Models
# ============================================

class SyntheticDataConfig(BaseModel):
    """Configuration for synthetic data generation."""
    seed: int = 42
    days: int = 365
    sample_rate_minutes: int = 10
    zones: List[str] = Field(default_factory=lambda: [
        "prod-01", "prod-02", "prod-03", "store-01", "store-02", "tech-01", "tech-02"
    ])
    parameters: List[str] = Field(default_factory=lambda: [
        "temperature", "humidity", "noise", "air_quality", "pm25", "pm10", "voltage"
    ])
    anomaly_ratio: float = 0.05
    drift_factor: float = 0.001
    correlation_strength: float = 0.7


# Zone parameter configurations for synthetic data
ZONE_PARAMETER_CONFIGS = {
    "prod-01": {"type": "production", "base_temp": 24, "temp_variance": 4, "base_humidity": 50, "humidity_variance": 10},
    "prod-02": {"type": "production", "base_temp": 25, "temp_variance": 5, "base_humidity": 48, "humidity_variance": 12},
    "prod-03": {"type": "production", "base_temp": 23, "temp_variance": 3, "base_humidity": 52, "humidity_variance": 8},
    "store-01": {"type": "storage", "base_temp": 18, "temp_variance": 2, "base_humidity": 40, "humidity_variance": 5},
    "store-02": {"type": "storage", "base_temp": 20, "temp_variance": 3, "base_humidity": 45, "humidity_variance": 8},
    "tech-01": {"type": "technical", "base_temp": 22, "temp_variance": 2, "base_humidity": 35, "humidity_variance": 5},
    "tech-02": {"type": "technical", "base_temp": 21, "temp_variance": 2, "base_humidity": 38, "humidity_variance": 6},
}

PARAMETER_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "noise": "dB",
    "air_quality": "AQI",
    "pm25": "µg/m³",
    "pm10": "µg/m³",
    "voltage": "V",
}

PARAMETER_RANGES = {
    "temperature": (-10, 50),
    "humidity": (0, 100),
    "noise": (30, 120),
    "air_quality": (0, 500),
    "pm25": (0, 150),
    "pm10": (0, 200),
    "voltage": (200, 250),
}

DEFAULT_THRESHOLDS = {
    "temperature": {"warning_min": 18, "warning_max": 28, "critical_min": 15, "critical_max": 35},
    "humidity": {"warning_min": 30, "warning_max": 70, "critical_min": 20, "critical_max": 85},
    "noise": {"warning_max": 80, "critical_max": 95},
    "air_quality": {"warning_max": 100, "critical_max": 150},
    "pm25": {"warning_max": 25, "critical_max": 50},
    "pm10": {"warning_max": 50, "critical_max": 100},
    "voltage": {"warning_min": 210, "warning_max": 240, "critical_min": 200, "critical_max": 250},
}