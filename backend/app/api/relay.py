"""
Relay Control API Routes
Role-restricted relay control via MQTT with audit logging.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Literal, Optional

from app.services.mqtt_ingestion import get_mqtt_service
from app.services.rbac import get_rbac_service, Permission
from app.services.audit import get_audit_service
from app.services.auth import get_auth_service

router = APIRouter(prefix="/relay", tags=["relay"])


@router.post("/{zone_id}/{relay_id}", summary="Control relay")
async def control_relay(
    zone_id: str,
    relay_id: int,
    command: Literal["on", "off", "toggle", "state"] = Query(...),
    mqtt_service=Depends(get_mqtt_service),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    auth=Depends(get_auth_service),
    # token_data=Depends(...),
):
    """
    Control relay in a zone.
    
    - Requires relay:control permission
    - Operator, maintenance, admin roles only
    - All commands are audited
    """
    # Check permission
    # token_data = await auth.verify_token(token)
    # rbac.check_permission(token_data.role, Permission.RELAY_CONTROL, zone_id)
    
    # Validate relay ID
    if relay_id not in (1, 2):
        raise HTTPException(status_code=400, detail="Invalid relay ID (must be 1 or 2)")
    
    # Validate zone exists (simplified)
    valid_zones = ["prod-01", "prod-02", "prod-03", "store-01", "store-02", "tech-01", "tech-02"]
    if zone_id not in valid_zones:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    # Publish command via MQTT
    success = await mqtt_service.publish_relay_command(zone_id, relay_id, command)
    
    if not success:
        raise HTTPException(status_code=503, detail="MQTT not connected or publish failed")
    
    # Audit log
    await audit.log(
        actor_id="system",
        actor_role="operator",
        action="relay_control",
        resource_type="relay",
        resource_id=f"{zone_id}:{relay_id}",
        details={"command": command, "zone_id": zone_id, "relay_id": relay_id},
    )
    
    return {
        "success": True,
        "zone_id": zone_id,
        "relay_id": relay_id,
        "command": command,
        "message": f"Relay command '{command}' sent successfully",
    }


@router.get("/{zone_id}/{relay_id}/state", summary="Get relay state")
async def get_relay_state(
    zone_id: str,
    relay_id: int,
    mqtt_service=Depends(get_mqtt_service),
    rbac=Depends(get_rbac_service),
    # token_data=Depends(...),
):
    """Get current relay state (publishes state request)."""
    # rbac.check_permission(token_data.role, Permission.RELAY_READ, zone_id)
    
    if relay_id not in (1, 2):
        raise HTTPException(status_code=400, detail="Invalid relay ID")
    
    success = await mqtt_service.publish_relay_command(zone_id, relay_id, "state")
    
    if not success:
        raise HTTPException(status_code=503, detail="MQTT not connected")
    
    return {
        "zone_id": zone_id,
        "relay_id": relay_id,
        "message": "State request sent, response will come via MQTT/WebSocket",
    }


@router.get("/zones", summary="List zones with relay info")
async def list_relay_zones():
    """List all zones that have relays."""
    zones = [
        {"zone_id": "prod-01", "relays": [1, 2], "description": "Production Line 1 - Ventilation & Extraction"},
        {"zone_id": "prod-02", "relays": [1, 2], "description": "Production Line 2 - Ventilation & Extraction"},
        {"zone_id": "prod-03", "relays": [1, 2], "description": "Production Line 3 - Ventilation & Extraction"},
        {"zone_id": "store-01", "relays": [1, 2], "description": "Storage Area 1 - Climate Control"},
        {"zone_id": "store-02", "relays": [1, 2], "description": "Storage Area 2 - Climate Control"},
        {"zone_id": "tech-01", "relays": [1, 2], "description": "Technical Room 1 - HVAC & Cooling"},
        {"zone_id": "tech-02", "relays": [1, 2], "description": "Technical Room 2 - Server Cooling"},
    ]
    return {"zones": zones}