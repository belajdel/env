"""
Report Models
"""

from datetime import datetime
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field
from bson import ObjectId

from .user import PyObjectId


REPORT_TYPES = ("hourly", "daily", "weekly", "monthly", "custom", "alert_summary", "ai_weekly")
REPORT_FORMATS = ("csv", "pdf", "json")


class ReportBase(BaseModel):
    """Base report model."""
    zone_id: Optional[str] = Field(None, max_length=50)
    report_type: Literal[REPORT_TYPES]
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    parameters: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None


class ReportCreate(ReportBase):
    """Model for creating a report."""
    format: Literal[REPORT_FORMATS] = "csv"
    start: datetime
    end: datetime


class ReportInDB(ReportBase):
    """Report model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    format: Literal[REPORT_FORMATS]
    start: datetime
    end: datetime
    generated_by: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    row_count: Optional[int] = None
    status: Literal["pending", "generating", "completed", "failed"] = "pending"
    error_message: Optional[str] = None
    generated_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }


class ReportPublic(ReportBase):
    """Report model for public API responses."""
    id: str = Field(..., alias="_id")
    format: Literal[REPORT_FORMATS]
    start: datetime
    end: datetime
    generated_by: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    row_count: Optional[int] = None
    status: Literal["pending", "generating", "completed", "failed"]
    error_message: Optional[str] = None
    generated_at: datetime
    completed_at: Optional[datetime] = None
    download_url: Optional[str] = None
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str, datetime: lambda v: v.isoformat()},
    }
    
    @classmethod
    def from_db(cls, report: ReportInDB) -> "ReportPublic":
        download_url = None
        if report.file_path and report.status == "completed":
            download_url = f"/api/reports/{report.id}/download"
        
        return cls(
            _id=str(report.id),
            zone_id=report.zone_id,
            report_type=report.report_type,
            title=report.title,
            description=report.description,
            parameters=report.parameters,
            filters=report.filters,
            format=report.format,
            start=report.start,
            end=report.end,
            generated_by=report.generated_by,
            file_path=report.file_path,
            file_size=report.file_size,
            row_count=report.row_count,
            status=report.status,
            error_message=report.error_message,
            generated_at=report.generated_at,
            completed_at=report.completed_at,
            download_url=download_url,
        )


class ReportQuery(BaseModel):
    """Query parameters for report listing."""
    zone_id: Optional[str] = None
    report_type: Optional[Literal[REPORT_TYPES]] = None
    generated_by: Optional[str] = None
    status: Optional[Literal["pending", "generating", "completed", "failed"]] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    limit: int = Field(default=50, le=200)
    offset: int = Field(default=0, ge=0)