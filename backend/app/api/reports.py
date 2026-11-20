"""
Reports API Routes
Generate, list, and download reports (CSV/PDF).
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime

from app.core.database import get_database, Collections
from app.services.rbac import get_rbac_service, Permission
from app.services.reports import get_report_service
from app.services.audit import get_audit_service
from app.models.report import ReportCreate, ReportPublic, ReportQuery, ReportType, ReportFormat
from bson import ObjectId

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportPublic, status_code=status.HTTP_201_CREATED, summary="Create report")
async def create_report(
    report_create: ReportCreate,
    report_service=Depends(get_report_service),
    audit=Depends(get_audit_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Create a new report generation job."""
    # rbac.check_permission(token_data.role, Permission.REPORT_CREATE)
    
    # user_id = token_data.user_id
    user_id = "current_user"  # Placeholder
    
    return await report_service.create_report(report_create, user_id)


@router.get("", response_model=List[ReportPublic], summary="List reports")
async def list_reports(
    zone_id: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
    generated_by: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    report_service=Depends(get_report_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """List reports with filters and pagination."""
    query = ReportQuery(
        zone_id=zone_id,
        report_type=report_type,
        generated_by=generated_by,
        status=status,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )
    return await report_service.list_reports(query)


@router.get("/{report_id}", response_model=ReportPublic, summary="Get report by ID")
async def get_report(
    report_id: str,
    report_service=Depends(get_report_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get report by ID."""
    report = await report_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/download", summary="Download report file")
async def download_report(
    report_id: str,
    report_service=Depends(get_report_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Download generated report file."""
    # rbac.check_permission(token_data.role, Permission.REPORT_DOWNLOAD)
    
    filepath = await report_service.get_download_path(report_id)
    if not filepath:
        raise HTTPException(status_code=404, detail="Report file not found or not ready")
    
    # Determine media type
    media_types = {
        "csv": "text/csv",
        "pdf": "application/pdf",
        "json": "application/json",
    }
    
    ext = filepath.suffix.lower().lstrip(".")
    media_type = media_types.get(ext, "application/octet-stream")
    
    return FileResponse(
        path=filepath,
        media_type=media_type,
        filename=filepath.name,
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete report")
async def delete_report(
    report_id: str,
    report_service=Depends(get_report_service),
    audit=Depends(get_audit_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Delete report and its file."""
    # rbac.check_permission(token_data.role, Permission.REPORT_DELETE)
    
    success = await report_service.delete_report(report_id)
    if not success:
        raise HTTPException(status_code=404, detail="Report not found")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="delete_report",
        resource_type="report",
        resource_id=report_id,
    )


@router.get("/types/list", summary="List report types")
async def list_report_types():
    return {"types": [t.value for t in ReportType]}


@router.get("/formats/list", summary="List report formats")
async def list_report_formats():
    return {"formats": [f.value for f in ReportFormat]}