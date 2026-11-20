"""
Device Models
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from bson import ObjectId

from .user import PyObjectId


DEVICE_STATUSES = ("online", "offline", "error", "maintenance")


class DeviceBase(BaseModel):
    """Base device model."""
    device_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    zone_id: str = Field(..., min_length=1, max_length=50)
    device_type: str = Field(..., min_length=1, max_length=50)
    firmware_version: str = Field(..., min_length=1, max_length=20)


class DeviceCreate(DeviceBase):
    """Model for creating a new device."""
    pass


class DeviceUpdate(BaseModel):
    """Model for updating a device (all fields optional)."""
    zone_id: Optional[str] = Field(None, min_length=1, max_length=50)
    device_type: Optional[str] = Field(None, min_length=1, max_length=50)
    firmware_version: Optional[str] = Field(None, min_length=1, max_length=20)
    status: Optional[Literal[DEVICE_STATUSES]] = None


class DeviceInDB(DeviceBase):
    """Device model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    status: Literal[DEVICE_STATUSES] = "offline"
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
    }


class DevicePublic(DeviceBase):
    """Device model for public API responses."""
    id: str = Field(..., alias="_id")
    status: Literal[DEVICE_STATUSES]
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str},
    }
    
    @classmethod
    def from_db(cls, device: DeviceInDB) -> "DevicePublic":
        return cls(
            _id=str(device.id),
            device_id=device.device_id,
            zone_id=device.zone_id,
            device_type=device.device_type,
            firmware_version=device.firmware_version,
            status=device.status,
            last_seen=device.last_seen,
            created_at=device.created_at,
            updated_at=device.updated_at,
        )


class DeviceStatusUpdate(BaseModel):
    """Model for device status updates from MQTT."""
    device_id: str
    status: Literal[DEVICE_STATUSES]
    timestamp: datetime
    firmware_version: Optional[str] = None
    ip_address: Optional[str] = None
    signal_strength: Optional[int] = None