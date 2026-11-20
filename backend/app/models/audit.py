"""
Audit Log Models
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId

from .user import PyObjectId


class AuditLogBase(BaseModel):
    """Base audit log model."""
    actor_id: str = Field(..., min_length=1, max_length=100)
    actor_role: str = Field(..., min_length=1, max_length=50)
    action: str = Field(..., min_length=1, max_length=100)
    resource_type: str = Field(..., min_length=1, max_length=100)
    resource_id: str = Field(..., min_length=1, max_length=200)
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = Field(None, max_length=45)
    user_agent: Optional[str] = Field(None, max_length=500)


class AuditLogCreate(AuditLogBase):
    """Model for creating an audit log entry."""
    pass


class AuditLogInDB(AuditLogBase):
    """Audit log model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    timestamp: datetime
    prev_hash: str = Field(..., min_length=64, max_length=64)
    hash: str = Field(..., min_length=64, max_length=64)
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class AuditLogPublic(AuditLogBase):
    """Audit log model for public API responses (admin only)."""
    id: str = Field(..., alias="_id")
    timestamp: datetime
    prev_hash: str
    hash: str
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }
    
    @classmethod
    def from_db(cls, audit: AuditLogInDB) -> "AuditLogPublic":
        return cls(
            _id=str(audit.id),
            actor_id=audit.actor_id,
            actor_role=audit.actor_role,
            action=audit.action,
            resource_type=audit.resource_type,
            resource_id=audit.resource_id,
            details=audit.details,
            ip_address=audit.ip_address,
            user_agent=audit.user_agent,
            timestamp=audit.timestamp,
            prev_hash=audit.prev_hash,
            hash=audit.hash,
        )


class AuditLogQuery(BaseModel):
    """Query parameters for audit log listing."""
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)
    verify_chain: bool = False