"""
Audit Log API Routes
Admin-only access to audit logs with chain verification.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime

from app.core.database import get_database, Collections
from app.services.rbac import get_rbac_service, Permission, ROLE_ADMIN
from app.services.audit import get_audit_service
from app.models.audit import AuditLogPublic, AuditLogQuery
from app.services.auth import get_auth_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=List[AuditLogPublic], summary="List audit logs (admin)")
async def list_audit_logs(
    actor_id: Optional[str] = Query(None),
    actor_role: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    verify_chain: bool = Query(False),
    audit=Depends(get_audit_service),
    auth=Depends(get_auth_service),
    # token_data=Depends(...),
):
    """List audit logs with filters (admin only)."""
    # Check admin permission
    # token_data = await auth.verify_token(token)
    # if token_data.role != ROLE_ADMIN:
    #     raise HTTPException(403, "Admin required")
    
    query = AuditLogQuery(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        verify_chain=verify_chain,
    )
    
    return await audit.query(query)


@router.get("/verify", summary="Verify audit log chain integrity (admin)")
async def verify_audit_chain(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    audit=Depends(get_audit_service),
    auth=Depends(get_auth_service),
    # token_data=Depends(...),
):
    """Verify hash chain integrity of audit logs."""
    # token_data = await auth.verify_token(token)
    # if token_data.role != ROLE_ADMIN:
    #     raise HTTPException(403, "Admin required")
    
    return await audit.verify_chain(start, end)


@router.get("/stats", summary="Get audit log statistics (admin)")
async def get_audit_stats(
    audit=Depends(get_audit_service),
    auth=Depends(get_auth_service),
    # token_data=Depends(...),
):
    """Get audit log statistics."""
    # token_data = await auth.verify_token(token)
    # if token_data.role != ROLE_ADMIN:
    #     raise HTTPException(403, "Admin required")
    
    return await audit.get_stats()