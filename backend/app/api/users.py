"""
User Management API Routes
Admin-only user CRUD operations.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional

from app.services.auth import get_auth_service
from app.services.rbac import get_rbac_service, Permission, require_admin
from app.services.audit import get_audit_service
from app.models.user import UserCreate, UserUpdate, UserPublic, ROLE_ADMIN

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED, summary="Create user (admin)")
async def create_user(
    user_create: UserCreate,
    auth=Depends(get_auth_service),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    token_data=Depends(require_admin()),
):
    """Create a new user (admin only)."""
    rbac.require_permission(token_data.role, Permission.USER_CREATE)
    
    try:
        user = await auth.create_user(user_create, token_data.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return UserPublic.from_db(user)


@router.get("", response_model=List[UserPublic], summary="List users (admin)")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    auth=Depends(get_auth_service),
    rbac=Depends(get_rbac_service),
    token_data=Depends(require_admin()),
):
    """List users with pagination and filters (admin only)."""
    rbac.require_permission(token_data.role, Permission.USER_LIST)
    
    users = await auth.list_users(skip=skip, limit=limit, role=role, is_active=is_active)
    return users


@router.get("/{user_id}", response_model=UserPublic, summary="Get user by ID (admin)")
async def get_user(
    user_id: str,
    auth=Depends(get_auth_service),
    rbac=Depends(get_rbac_service),
    token_data=Depends(require_admin()),
):
    """Get user by ID (admin only)."""
    rbac.require_permission(token_data.role, Permission.USER_READ)
    
    user = await auth.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserPublic.from_db(user)


@router.patch("/{user_id}", response_model=UserPublic, summary="Update user (admin)")
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    auth=Depends(get_auth_service),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    token_data=Depends(require_admin()),
):
    """Update user (admin only)."""
    rbac.require_permission(token_data.role, Permission.USER_UPDATE)
    
    user = await auth.update_user(user_id, user_update, token_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserPublic.from_db(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user (admin)")
async def delete_user(
    user_id: str,
    auth=Depends(get_auth_service),
    rbac=Depends(get_rbac_service),
    audit=Depends(get_audit_service),
    token_data=Depends(require_admin()),
):
    """Deactivate user (admin only)."""
    rbac.require_permission(token_data.role, Permission.USER_DELETE)
    
    # Prevent self-deletion
    if user_id == token_data.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    success = await auth.delete_user(user_id, token_data.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")