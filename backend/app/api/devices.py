"""
Device Management API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional

from app.core.database import get_database, Collections
from app.services.rbac import get_rbac_service, Permission
from app.services.audit import get_audit_service
from app.models.device import DeviceCreate, DeviceUpdate, DevicePublic, DeviceInDB, DeviceStatusUpdate, DEVICE_STATUSES
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", response_model=DevicePublic, status_code=status.HTTP_201_CREATED, summary="Create device")
async def create_device(
    device_create: DeviceCreate,
    db=Depends(get_database),
    audit=Depends(get_audit_service),
):
    """Register a new device."""
    # Check if device_id already exists
    existing = await db[Collections.DEVICES].find_one({"device_id": device_create.device_id})
    if existing:
        raise HTTPException(status_code=400, detail="Device ID already exists")
    
    # Verify zone exists
    zone = await db[Collections.ZONES].find_one({"zone_id": device_create.zone_id})
    if not zone:
        raise HTTPException(status_code=400, detail="Zone not found")
    
    now = datetime.now(timezone.utc)
    device = DeviceInDB(
        **device_create.model_dump(),
        status="offline",
        created_at=now,
        updated_at=now,
    )
    
    result = await db[Collections.DEVICES].insert_one(device.model_dump(by_alias=True))
    device.id = result.inserted_id
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="create_device",
        resource_type="device",
        resource_id=device_create.device_id,
        details=device_create.model_dump(),
    )
    
    return DevicePublic.from_db(device)


@router.get("", response_model=List[DevicePublic], summary="List devices")
async def list_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    zone_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db=Depends(get_database),
):
    """List devices with pagination and filters."""
    query = {}
    if zone_id:
        query["zone_id"] = zone_id
    if status:
        query["status"] = status
    
    cursor = db[Collections.DEVICES].find(query).sort("device_id", 1).skip(skip).limit(limit)
    devices = []
    async for doc in cursor:
        devices.append(DevicePublic.from_db(DeviceInDB(**doc)))
    return devices


@router.get("/{device_id}", response_model=DevicePublic, summary="Get device by ID")
async def get_device(
    device_id: str,
    db=Depends(get_database),
):
    """Get device by ID."""
    doc = await db[Collections.DEVICES].find_one({"device_id": device_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Device not found")
    return DevicePublic.from_db(DeviceInDB(**doc))


@router.patch("/{device_id}", response_model=DevicePublic, summary="Update device")
async def update_device(
    device_id: str,
    device_update: DeviceUpdate,
    db=Depends(get_database),
    audit=Depends(get_audit_service),
):
    """Update device."""
    update_data = device_update.model_dump(exclude_unset=True)
    if not update_data:
        doc = await db[Collections.DEVICES].find_one({"device_id": device_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Device not found")
        return DevicePublic.from_db(DeviceInDB(**doc))
    
    # Verify zone if being updated
    if "zone_id" in update_data:
        zone = await db[Collections.ZONES].find_one({"zone_id": update_data["zone_id"]})
        if not zone:
            raise HTTPException(status_code=400, detail="Zone not found")
    
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    result = await db[Collections.DEVICES].find_one_and_update(
        {"device_id": device_id},
        {"$set": update_data},
        return_document=True,
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="update_device",
        resource_type="device",
        resource_id=device_id,
        details=update_data,
    )
    
    return DevicePublic.from_db(DeviceInDB(**result))


@router.patch("/{device_id}/status", response_model=DevicePublic, summary="Update device status")
async def update_device_status(
    device_id: str,
    status_update: DeviceStatusUpdate,
    db=Depends(get_database),
):
    """Update device status (called from MQTT ingestion)."""
    if status_update.device_id != device_id:
        raise HTTPException(status_code=400, detail="Device ID mismatch")
    
    update_data = {
        "status": status_update.status,
        "last_seen": status_update.timestamp,
        "updated_at": datetime.now(timezone.utc),
    }
    
    if status_update.firmware_version:
        update_data["firmware_version"] = status_update.firmware_version
    
    result = await db[Collections.DEVICES].find_one_and_update(
        {"device_id": device_id},
        {"$set": update_data},
        return_document=True,
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return DevicePublic.from_db(DeviceInDB(**result))


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete device")
async def delete_device(
    device_id: str,
    db=Depends(get_database),
    audit=Depends(get_audit_service),
):
    """Delete device."""
    result = await db[Collections.DEVICES].delete_one({"device_id": device_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    
    await audit.log(
        actor_id="system",
        actor_role="system",
        action="delete_device",
        resource_type="device",
        resource_id=device_id,
    )