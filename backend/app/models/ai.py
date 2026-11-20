"""
AI Service Models
"""

from datetime import datetime
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field
from bson import ObjectId

from .user import PyObjectId
from .measurement import VALID_PARAMETERS


PREDICTION_TYPES = ("threshold_breach", "anomaly", "risk_score")
MODEL_TYPES = ("isolation_forest", "autoencoder", "lstm")


class AIPredictionBase(BaseModel):
    """Base AI prediction model."""
    zone_id: str = Field(..., min_length=1, max_length=50)
    prediction_type: Literal[PREDICTION_TYPES]
    model_type: Literal[MODEL_TYPES]
    model_version: str
    horizon_minutes: int = Field(..., ge=1, le=1440)  # 1 min to 24 hours
    value: float
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: Optional[Dict[str, Any]] = None


class AIPredictionInDB(AIPredictionBase):
    """AI prediction model as stored in database (time-series)."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    timestamp: datetime
    valid_until: datetime
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class AIPredictionPublic(AIPredictionBase):
    """AI prediction model for public API responses."""
    id: str = Field(..., alias="_id")
    timestamp: datetime
    valid_until: datetime
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }
    
    @classmethod
    def from_db(cls, pred: AIPredictionInDB) -> "AIPredictionPublic":
        return cls(
            _id=str(pred.id),
            zone_id=pred.zone_id,
            prediction_type=pred.prediction_type,
            model_type=pred.model_type,
            model_version=pred.model_version,
            horizon_minutes=pred.horizon_minutes,
            value=pred.value,
            confidence=pred.confidence,
            metadata=pred.metadata,
            timestamp=pred.timestamp,
            valid_until=pred.valid_until,
        )


class RiskScoreBase(BaseModel):
    """Base risk score model."""
    zone_id: str = Field(..., min_length=1, max_length=50)
    score: int = Field(..., ge=0, le=100)
    level: Literal["low", "medium", "high", "critical"]
    factors: Dict[str, float] = Field(default_factory=dict)  # factor -> contribution
    model_version: str
    metadata: Optional[Dict[str, Any]] = None


class RiskScoreInDB(RiskScoreBase):
    """Risk score model as stored in database (time-series)."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    timestamp: datetime
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class RiskScorePublic(RiskScoreBase):
    """Risk score model for public API responses."""
    id: str = Field(..., alias="_id")
    timestamp: datetime
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }
    
    @classmethod
    def from_db(cls, risk: RiskScoreInDB) -> "RiskScorePublic":
        return cls(
            _id=str(risk.id),
            zone_id=risk.zone_id,
            score=risk.score,
            level=risk.level,
            factors=risk.factors,
            model_version=risk.model_version,
            metadata=risk.metadata,
            timestamp=risk.timestamp,
        )


# AI Service API Models (for HTTP communication)

class AIPredictRequest(BaseModel):
    """Request model for /predict endpoint."""
    zone_id: str
    horizon_minutes: int = Field(default=30, ge=1, le=1440)
    parameters: Optional[List[str]] = None


class AIAnomalyRequest(BaseModel):
    """Request model for /anomaly endpoint."""
    zone_id: str
    measurements: Dict[str, float]  # parameter -> value
    timestamp: datetime


class AIRetrainRequest(BaseModel):
    """Request model for /retrain endpoint."""
    model_type: Optional[Literal[MODEL_TYPES]] = None
    force: bool = False


class AIPredictResponse(BaseModel):
    """Response model for /predict endpoint."""
    zone_id: str
    predictions: Dict[str, AIPredictionPublic]
    generated_at: datetime


class AIAnomalyResponse(BaseModel):
    """Response model for /anomaly endpoint."""
    zone_id: str
    is_anomaly: bool
    anomaly_score: float
    details: Dict[str, Any]
    generated_at: datetime


class AIRiskResponse(BaseModel):
    """Response model for /risk/{zone_id} endpoint."""
    zone_id: str
    risk_score: RiskScorePublic
    generated_at: datetime


class AIRetrainResponse(BaseModel):
    """Response model for /retrain endpoint."""
    success: bool
    model_type: str
    model_version: str
    metrics: Dict[str, float]
    message: str
    started_at: datetime
    completed_at: Optional[datetime] = None


class AIWeeklyReportResponse(BaseModel):
    """Response model for /report/weekly endpoint."""
    week_start: datetime
    week_end: datetime
    zones: Dict[str, Dict[str, Any]]
    summary: Dict[str, Any]
    generated_at: datetime