"""
Zone Management API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional

from app.core.database import get_database, Collections
from app.services.rbac import get_rbac_service, Permission
from app.services.audit import get_audit_service
from app.models.zone import ZoneCreate, ZoneUpdate, ZonePublic, ZoneInDB, ZONE_TYPES
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter(prefix="/zones", tags=["zones"])


@router.post("", response_model=ZonePublic, status_code=status.HTTP_201_CREATED, summary="Create zone")
async def create_zone(
    zone_create: ZoneCreate,
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    token_data=Depends(lambda: rbac.check_permission(token_data.role, Permission.ZONE_CREATE) for token_data in [None]) or Depends(),
):
    """Create a new zone."""
    # Check permission
    from app.services.auth import get_auth_service
    auth = get_auth_service()
    token_data = await auth.verify_token(token_data) if hasattr(token_data, 'user_id') else None
    # This is a simplified check - in real route, use proper dependency
    
    # Check if zone_id already exists
    existing = await db[Collections.ZONES].find_one({"zone_id": zone_create.zone_id})
    if existing:
        raise HTTPException(status_code=400, detail="Zone ID already exists")
    
    now = datetime.now(timezone.utc)
    zone = ZoneInDB(
        **zone_create.model_dump(),
        created_at=now,
        updated_at=now,
    )
    
    result = await db[Collections.ZONES].insert_one(zone.model_dump(by_alias=True))
    zone.id = result.inserted_id
    
    # Audit
    from app.services.auth import get_auth_service
    # token_data would come from proper dependency
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="create_zone",
        resource_type="zone",
        resource_id=zone_create.zone_id,
        details=zone_create.model_dump(),
    )
    
    return ZonePublic.from_db(zone)


@router.get("", response_model=List[ZonePublic], summary="List zones")
async def list_zones(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    type: Optional[str] = Query(None),
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    token_data=Depends(lambda: None),  # Placeholder
):
    """List zones with pagination."""
    # Simplified - in real implementation, use proper auth dependency
    query = {}
    if type:
        query["type"] = type
    
    cursor = db[Collections.ZONES].find(query).sort("zone_id", 1).skip(skip).limit(limit)
    zones = []
    async for doc in cursor:
        zones.append(ZonePublic.from_db(ZoneInDB(**doc)))
    return zones


@router.get("/{zone_id}", response_model=ZonePublic, summary="Get zone by ID")
async def get_zone(
    zone_id: str,
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    token_data=Depends(lambda: None),
):
    """Get zone by ID."""
    doc = await db[Collections.ZONES].find_one({"zone_id": zone_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Zone not found")
    return ZonePublic.from_db(ZoneInDB(**doc))


@router.patch("/{zone_id}", response_model=ZonePublic, summary="Update zone")
async def update_zone(
    zone_id: str,
    zone_update: ZoneUpdate,
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    token_data=Depends(lambda: None),
):
    """Update zone."""
    update_data = zone_update.model_dump(exclude_unset=True)
    if not update_data:
        doc = await db[Collections.ZONES].find_one({"zone_id": zone_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Zone not found")
        return ZonePublic.from_db(ZoneInDB(**doc))
    
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    result = await db[Collections.ZONES].find_one_and_update(
        {"zone_id": zone_id},
        {"$set": update_data},
        return_document=True,
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    # Audit
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="update_zone",
        resource_type="zone",
        resource_id=zone_id,
        details=update_data,
    )
    
    return ZonePublic.from_db(ZoneInDB(**result))


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete zone")
async def delete_zone(
    zone_id: str,
    db=Depends(get_database),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    token_data=Depends(lambda: None),
):
    """Delete zone."""
    result = await db[Collections.ZONES].delete_one({"zone_id": zone_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="delete_zone",
        resource_type="zone",
        resource_id=zone_id,
    )


# Note: The above routes have placeholder auth dependencies. 
# In production, each route should use proper Depends() with token_data extraction.
# This is a skeleton - the full implementation with proper auth is in the main.py integration.