"""
Alerts API Routes
Alert history, acknowledgment, resolution.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime

from app.core.database import get_database, Collections
from app.services.rbac import get_rbac_service, Permission
from app.services.alerts import get_alert_engine
from app.services.audit import get_audit_service
from app.models.alert import AlertPublic, AlertUpdate, AlertQuery, AlertSummary, ALERT_LEVELS, ALERT_STATUSES
from bson import ObjectId

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=List[AlertPublic], summary="Get alert history")
async def list_alerts(
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """List alerts with filters and pagination."""
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if parameter:
        query["parameter"] = parameter
    if level:
        query["level"] = level
    if status:
        query["status"] = status
    if start or end:
        query["created_at"] = {}
        if start:
            query["created_at"]["$gte"] = start
        if end:
            query["created_at"]["$lte"] = end
    
    cursor = db[Collections.ALERTS].find(query).sort("created_at", -1).skip(offset).limit(limit)
    
    alerts = []
    async for doc in cursor:
        from app.models.alert import AlertInDB
        alerts.append(AlertPublic.from_db(AlertInDB(**doc)))
    
    return alerts


@router.get("/summary", response_model=AlertSummary, summary="Get alert summary for dashboard")
async def get_alert_summary(
    db=Depends(get_database),
    alert_engine=Depends(get_alert_engine),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get alert summary statistics."""
    return await alert_engine.get_alert_summary()


@router.get("/active", response_model=List[AlertPublic], summary="Get active alerts")
async def get_active_alerts(
    zone_id: Optional[str] = Query(None),
    alert_engine=Depends(get_alert_engine),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get all active (open/acknowledged) alerts."""
    return await alert_engine.get_active_alerts(zone_id)


@router.get("/{alert_id}", response_model=AlertPublic, summary="Get alert by ID")
async def get_alert(
    alert_id: str,
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get alert by ID."""
    doc = await db[Collections.ALERTS].find_one({"_id": ObjectId(alert_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Alert not found")
    from app.models.alert import AlertInDB
    return AlertPublic.from_db(AlertInDB(**doc))


@router.post("/{alert_id}/acknowledge", response_model=AlertPublic, summary="Acknowledge alert")
async def acknowledge_alert(
    alert_id: str,
    alert_engine=Depends(get_alert_engine),
    audit=Depends(get_audit_service),
    # token_data=Depends(...),
):
    """Acknowledge an alert."""
    # user_id = token_data.user_id
    user_id = "current_user"  # Placeholder
    
    alert = await alert_engine.acknowledge_alert(alert_id, user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")
    
    await audit.log(
        actor_id=user_id,
        actor_role="operator",
        action="acknowledge_alert",
        resource_type="alert",
        resource_id=alert_id,
    )
    
    return alert


@router.post("/{alert_id}/resolve", response_model=AlertPublic, summary="Resolve alert")
async def resolve_alert(
    alert_id: str,
    update: AlertUpdate,
    alert_engine=Depends(get_alert_engine),
    audit=Depends(get_audit_service),
    # token_data=Depends(...),
):
    """Resolve an alert."""
    # user_id = token_data.user_id
    user_id = "current_user"  # Placeholder
    
    alert = await alert_engine.resolve_alert(alert_id, user_id, update.resolution_notes)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found or not active")
    
    await audit.log(
        actor_id=user_id,
        actor_role="operator",
        action="resolve_alert",
        resource_type="alert",
        resource_id=alert_id,
        details={"notes": update.resolution_notes},
    )
    
    return alert


@router.get("/levels/list", summary="List valid alert levels")
async def list_alert_levels():
    return {"levels": ALERT_LEVELS}


@router.get("/statuses/list", summary="List valid alert statuses")
async def list_alert_statuses():
    return {"statuses": ALERT_STATUSES}