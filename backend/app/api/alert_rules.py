"""
Alert Rules API Routes
CRUD for threshold and correlation alert rules.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional

from app.core.database import get_database, Collections
from app.services.rbac import get_rbac_service, Permission
from app.services.audit import get_audit_service
from app.models.alert import AlertRuleCreate, AlertRuleUpdate, AlertRulePublic, AlertRuleInDB, VALID_PARAMETERS
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.post("", response_model=AlertRulePublic, status_code=status.HTTP_201_CREATED, summary="Create alert rule")
async def create_alert_rule(
    rule_create: AlertRuleCreate,
    db=Depends(get_database),
    audit=Depends(get_audit_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Create a new alert rule."""
    # Check permission
    # rbac.check_permission(token_data.role, Permission.ALERT_RULE_CREATE, rule_create.zone_id)
    
    # Check if rule already exists
    existing = await db[Collections.ALERT_RULES].find_one({
        "zone_id": rule_create.zone_id,
        "parameter": rule_create.parameter,
    })
    if existing:
        raise HTTPException(status_code=400, detail="Alert rule already exists for this zone/parameter")
    
    # Validate zone exists
    zone = await db[Collections.ZONES].find_one({"zone_id": rule_create.zone_id})
    if not zone:
        raise HTTPException(status_code=400, detail="Zone not found")
    
    now = datetime.now(timezone.utc)
    rule = AlertRuleInDB(
        **rule_create.model_dump(),
        created_at=now,
        updated_at=now,
    )
    
    result = await db[Collections.ALERT_RULES].insert_one(rule.model_dump(by_alias=True))
    rule.id = result.inserted_id
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="create_alert_rule",
        resource_type="alert_rule",
        resource_id=f"{rule_create.zone_id}:{rule_create.parameter}",
        details=rule_create.model_dump(),
    )
    
    return AlertRulePublic.from_db(rule)


@router.get("", response_model=List[AlertRulePublic], summary="List alert rules")
async def list_alert_rules(
    zone_id: Optional[str] = Query(None),
    parameter: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """List alert rules with filters."""
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if parameter:
        query["parameter"] = parameter
    if enabled is not None:
        query["enabled"] = enabled
    
    cursor = db[Collections.ALERT_RULES].find(query).sort([("zone_id", 1), ("parameter", 1)]).skip(skip).limit(limit)
    
    rules = []
    async for doc in cursor:
        rules.append(AlertRulePublic.from_db(AlertRuleInDB(**doc)))
    return rules


@router.get("/{zone_id}/{parameter}", response_model=AlertRulePublic, summary="Get alert rule")
async def get_alert_rule(
    zone_id: str,
    parameter: str,
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get alert rule for a zone/parameter."""
    doc = await db[Collections.ALERT_RULES].find_one({
        "zone_id": zone_id,
        "parameter": parameter,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return AlertRulePublic.from_db(AlertRuleInDB(**doc))


@router.patch("/{zone_id}/{parameter}", response_model=AlertRulePublic, summary="Update alert rule")
async def update_alert_rule(
    zone_id: str,
    parameter: str,
    rule_update: AlertRuleUpdate,
    db=Depends(get_database),
    audit=Depends(get_audit_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Update alert rule."""
    # rbac.check_permission(token_data.role, Permission.ALERT_RULE_UPDATE, zone_id)
    
    update_data = rule_update.model_dump(exclude_unset=True)
    if not update_data:
        doc = await db[Collections.ALERT_RULES].find_one({"zone_id": zone_id, "parameter": parameter})
        if not doc:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        return AlertRulePublic.from_db(AlertRuleInDB(**doc))
    
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    result = await db[Collections.ALERT_RULES].find_one_and_update(
        {"zone_id": zone_id, "parameter": parameter},
        {"$set": update_data},
        return_document=True,
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="update_alert_rule",
        resource_type="alert_rule",
        resource_id=f"{zone_id}:{parameter}",
        details=update_data,
    )
    
    return AlertRulePublic.from_db(AlertRuleInDB(**result))


@router.delete("/{zone_id}/{parameter}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete alert rule")
async def delete_alert_rule(
    zone_id: str,
    parameter: str,
    db=Depends(get_database),
    audit=Depends(get_audit_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Delete alert rule."""
    # rbac.check_permission(token_data.role, Permission.ALERT_RULE_DELETE, zone_id)
    
    result = await db[Collections.ALERT_RULES].delete_one({
        "zone_id": zone_id,
        "parameter": parameter,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="delete_alert_rule",
        resource_type="alert_rule",
        resource_id=f"{zone_id}:{parameter}",
    )


@router.get("/parameters/list", summary="List valid parameters")
async def list_parameters():
    return {"parameters": VALID_PARAMETERS}