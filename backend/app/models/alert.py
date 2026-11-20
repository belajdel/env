"""
Alert Models
"""

from datetime import datetime
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId

from .user import PyObjectId
from .measurement import VALID_PARAMETERS


ALERT_LEVELS = ("info", "warning", "critical", "predictive")
ALERT_STATUSES = ("open", "acknowledged", "resolved")


class AlertRuleBase(BaseModel):
    """Base alert rule model."""
    zone_id: str = Field(..., min_length=1, max_length=50)
    parameter: Literal[VALID_PARAMETERS]
    warning_min: Optional[float] = None
    warning_max: Optional[float] = None
    critical_min: Optional[float] = None
    critical_max: Optional[float] = None
    min_duration_sec: int = Field(default=60, ge=0, le=86400)
    correlation_rules: List[str] = Field(default_factory=list)
    enabled: bool = True
    
    @field_validator("correlation_rules")
    @classmethod
    def validate_correlation_rules(cls, v: List[str]) -> List[str]:
        for param in v:
            if param not in VALID_PARAMETERS:
                raise ValueError(f"Invalid correlation parameter: {param}")
        return v
    
    @field_validator("warning_min", "warning_max", "critical_min", "critical_max", mode="before")
    @classmethod
    def validate_thresholds(cls, v):
        if v is not None and not isinstance(v, (int, float)):
            raise ValueError("Threshold must be a number")
        return v


class AlertRuleCreate(AlertRuleBase):
    """Model for creating an alert rule."""
    pass


class AlertRuleUpdate(BaseModel):
    """Model for updating an alert rule (all fields optional)."""
    warning_min: Optional[float] = None
    warning_max: Optional[float] = None
    critical_min: Optional[float] = None
    critical_max: Optional[float] = None
    min_duration_sec: Optional[int] = Field(None, ge=0, le=86400)
    correlation_rules: Optional[List[str]] = None
    enabled: Optional[bool] = None


class AlertRuleInDB(AlertRuleBase):
    """Alert rule model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class AlertRulePublic(AlertRuleBase):
    """Alert rule model for public API responses."""
    id: str = Field(..., alias="_id")
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }
    
    @classmethod
    def from_db(cls, rule: AlertRuleInDB) -> "AlertRulePublic":
        return cls(
            _id=str(rule.id),
            zone_id=rule.zone_id,
            parameter=rule.parameter,
            warning_min=rule.warning_min,
            warning_max=rule.warning_max,
            critical_min=rule.critical_min,
            critical_max=rule.critical_max,
            min_duration_sec=rule.min_duration_sec,
            correlation_rules=rule.correlation_rules,
            enabled=rule.enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )


class AlertBase(BaseModel):
    """Base alert model."""
    zone_id: str = Field(..., min_length=1, max_length=50)
    parameter: Literal[VALID_PARAMETERS]
    level: Literal[ALERT_LEVELS]
    value: float
    threshold: float
    unit: str
    message: str
    metadata: Optional[Dict[str, Any]] = None


class AlertCreate(AlertBase):
    """Model for creating an alert."""
    rule_id: Optional[str] = None
    ai_prediction_id: Optional[str] = None


class AlertUpdate(BaseModel):
    """Model for updating an alert (acknowledge/resolve)."""
    status: Optional[Literal[ALERT_STATUSES]] = None
    acknowledged_by: Optional[str] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None


class AlertInDB(AlertBase):
    """Alert model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    rule_id: Optional[PyObjectId] = None
    ai_prediction_id: Optional[PyObjectId] = None
    status: Literal[ALERT_STATUSES] = "open"
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class AlertPublic(AlertBase):
    """Alert model for public API responses."""
    id: str = Field(..., alias="_id")
    rule_id: Optional[str] = None
    ai_prediction_id: Optional[str] = None
    status: Literal[ALERT_STATUSES]
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }
    
    @classmethod
    def from_db(cls, alert: AlertInDB) -> "AlertPublic":
        return cls(
            _id=str(alert.id),
            zone_id=alert.zone_id,
            parameter=alert.parameter,
            level=alert.level,
            value=alert.value,
            threshold=alert.threshold,
            unit=alert.unit,
            message=alert.message,
            metadata=alert.metadata,
            rule_id=str(alert.rule_id) if alert.rule_id else None,
            ai_prediction_id=str(alert.ai_prediction_id) if alert.ai_prediction_id else None,
            status=alert.status,
            acknowledged_by=alert.acknowledged_by,
            acknowledged_at=alert.acknowledged_at,
            resolved_by=alert.resolved_by,
            resolved_at=alert.resolved_at,
            resolution_notes=alert.resolution_notes,
            created_at=alert.created_at,
            updated_at=alert.updated_at,
        )


class AlertQuery(BaseModel):
    """Query parameters for alert history."""
    zone_id: Optional[str] = None
    parameter: Optional[Literal[VALID_PARAMETERS]] = None
    level: Optional[Literal[ALERT_LEVELS]] = None
    status: Optional[Literal[ALERT_STATUSES]] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)


class AlertSummary(BaseModel):
    """Alert summary for dashboard."""
    total_open: int
    total_acknowledged: int
    total_resolved_today: int
    by_level: Dict[str, int]
    by_zone: Dict[str, int]
    recent_critical: List[AlertPublic]