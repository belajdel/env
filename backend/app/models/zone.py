"""
Zone Models
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from bson import ObjectId

from .user import PyObjectId


ZONE_TYPES = ("production", "storage", "technical")


class ZoneBase(BaseModel):
    """Base zone model."""
    zone_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal[ZONE_TYPES]
    location: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)


class ZoneCreate(ZoneBase):
    """Model for creating a new zone."""
    pass


class ZoneUpdate(BaseModel):
    """Model for updating a zone (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[Literal[ZONE_TYPES]] = None
    location: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)


class ZoneInDB(ZoneBase):
    """Zone model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
    }


class ZonePublic(ZoneBase):
    """Zone model for public API responses."""
    id: str = Field(..., alias="_id")
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str},
    }
    
    @classmethod
    def from_db(cls, zone: ZoneInDB) -> "ZonePublic":
        return cls(
            _id=str(zone.id),
            zone_id=zone.zone_id,
            name=zone.name,
            type=zone.type,
            location=zone.location,
            description=zone.description,
            created_at=zone.created_at,
            updated_at=zone.updated_at,
        )