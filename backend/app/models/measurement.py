"""
Measurement Models
"""

from datetime import datetime
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
from bson import ObjectId

from .user import PyObjectId


VALID_PARAMETERS = (
    "temperature", "humidity", "noise", "air_quality",
    "pm25", "pm10", "voltage"
)

PARAMETER_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "noise": "dB",
    "air_quality": "ppm",
    "pm25": "μg/m³",
    "pm10": "μg/m³",
    "voltage": "V",
}


class MeasurementBase(BaseModel):
    """Base measurement model."""
    zone_id: str = Field(..., min_length=1, max_length=50)
    parameter: Literal[VALID_PARAMETERS]
    value: float
    unit: str
    device_id: Optional[str] = Field(None, max_length=50)
    metadata: Optional[Dict[str, Any]] = None


class MeasurementCreate(MeasurementBase):
    """Model for creating a measurement (from MQTT)."""
    timestamp: datetime
    
    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str, info) -> str:
        if info.data.get("parameter") and v != PARAMETER_UNITS.get(info.data["parameter"]):
            raise ValueError(f"Invalid unit for parameter {info.data['parameter']}")
        return v
    
    @field_validator("value")
    @classmethod
    def validate_value(cls, v: float, info) -> float:
        param = info.data.get("parameter")
        if param:
            ranges = {
                "temperature": (-40, 85),
                "humidity": (0, 100),
                "noise": (30, 130),
                "air_quality": (0, 10000),
                "pm25": (0, 500),
                "pm10": (0, 1000),
                "voltage": (0, 300),
            }
            if param in ranges:
                min_v, max_v = ranges[param]
                if not (min_v <= v <= max_v):
                    raise ValueError(f"Value {v} out of range for {param} ({min_v}-{max_v})")
        return v


class MeasurementInDB(MeasurementBase):
    """Measurement model as stored in database (time-series)."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    timestamp: datetime
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class MeasurementPublic(MeasurementBase):
    """Measurement model for public API responses."""
    id: str = Field(..., alias="_id")
    timestamp: datetime
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }
    
    @classmethod
    def from_db(cls, measurement: MeasurementInDB) -> "MeasurementPublic":
        return cls(
            _id=str(measurement.id),
            zone_id=measurement.zone_id,
            parameter=measurement.parameter,
            value=measurement.value,
            unit=measurement.unit,
            device_id=measurement.device_id,
            metadata=measurement.metadata,
            timestamp=measurement.timestamp,
        )


class MeasurementAggregate(BaseModel):
    """1-minute aggregate measurement."""
    zone_id: str
    parameter: Literal[VALID_PARAMETERS]
    unit: str
    count: int
    min: float
    max: float
    avg: float
    std: Optional[float] = None
    timestamp: datetime  # Start of the minute bucket
    
    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }


class MeasurementQuery(BaseModel):
    """Query parameters for measurement history."""
    zone_id: str
    parameter: Literal[VALID_PARAMETERS]
    start: datetime
    end: datetime
    aggregate: bool = False
    limit: int = Field(default=1000, le=10000)
    offset: int = Field(default=0, ge=0)


class MeasurementStats(BaseModel):
    """Statistical summary of measurements."""
    zone_id: str
    parameter: Literal[VALID_PARAMETERS]
    unit: str
    count: int
    min: float
    max: float
    avg: float
    std: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_95: float
    percentile_99: float
    start: datetime
    end: datetime