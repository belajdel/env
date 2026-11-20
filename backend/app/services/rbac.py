"""
RBAC Service
Role-based access control with explicit permissions for every route.
"""

from enum import Enum
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field

from app.models.user import ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST
from app.core.logging import get_logger

logger = get_logger(__name__)


class Permission(str, Enum):
    """System permissions."""
    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_LIST = "user:list"
    
    # Zone management
    ZONE_CREATE = "zone:create"
    ZONE_READ = "zone:read"
    ZONE_UPDATE = "zone:update"
    ZONE_DELETE = "zone:delete"
    ZONE_LIST = "zone:list"
    
    # Device management
    DEVICE_CREATE = "device:create"
    DEVICE_READ = "device:read"
    DEVICE_UPDATE = "device:update"
    DEVICE_DELETE = "device:delete"
    DEVICE_LIST = "device:list"
    
    # Measurement access
    MEASUREMENT_READ = "measurement:read"
    MEASUREMENT_AGGREGATE = "measurement:aggregate"
    MEASUREMENT_EXPORT = "measurement:export"
    
    # Alert management
    ALERT_READ = "alert:read"
    ALERT_ACKNOWLEDGE = "alert:acknowledge"
    ALERT_RESOLVE = "alert:resolve"
    ALERT_RULE_CREATE = "alert_rule:create"
    ALERT_RULE_READ = "alert_rule:read"
    ALERT_RULE_UPDATE = "alert_rule:update"
    ALERT_RULE_DELETE = "alert_rule:delete"
    ALERT_LIST = "alert:list"
    ALERT_EXPORT = "alert:export"
    
    # Relay control
    RELAY_CONTROL = "relay:control"
    RELAY_READ = "relay:read"
    
    # AI service
    AI_PREDICT = "ai:predict"
    AI_ANOMALY = "ai:anomaly"
    AI_RISK = "ai:risk"
    AI_RETRAIN = "ai:retrain"
    AI_REPORT = "ai:report"
    
    # Reports
    REPORT_CREATE = "report:create"
    REPORT_READ = "report:read"
    REPORT_DOWNLOAD = "report:download"
    REPORT_DELETE = "report:delete"
    REPORT_LIST = "report:list"
    
    # Audit logs
    AUDIT_READ = "audit:read"
    AUDIT_VERIFY = "audit:verify"
    
    # System
    SYSTEM_HEALTH = "system:health"
    SYSTEM_CONFIG = "system:config"


@dataclass
class RolePermissions:
    """Permissions assigned to a role."""
    role: str
    permissions: Set[Permission] = field(default_factory=set)
    zone_access: Optional[List[str]] = None  # None = all zones
    
    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions
    
    def has_zone_access(self, zone_id: str) -> bool:
        if self.zone_access is None:
            return True
        return zone_id in self.zone_access


# Define role permissions (explicit, no wildcards)
ROLE_PERMISSIONS_MAP: Dict[str, RolePermissions] = {
    ROLE_ADMIN: RolePermissions(
        role=ROLE_ADMIN,
        permissions={
            # All permissions
            Permission.USER_CREATE, Permission.USER_READ, Permission.USER_UPDATE,
            Permission.USER_DELETE, Permission.USER_LIST,
            Permission.ZONE_CREATE, Permission.ZONE_READ, Permission.ZONE_UPDATE,
            Permission.ZONE_DELETE, Permission.ZONE_LIST,
            Permission.DEVICE_CREATE, Permission.DEVICE_READ, Permission.DEVICE_UPDATE,
            Permission.DEVICE_DELETE, Permission.DEVICE_LIST,
            Permission.MEASUREMENT_READ, Permission.MEASUREMENT_AGGREGATE,
            Permission.MEASUREMENT_EXPORT,
            Permission.ALERT_READ, Permission.ALERT_ACKNOWLEDGE, Permission.ALERT_RESOLVE,
            Permission.ALERT_RULE_CREATE, Permission.ALERT_RULE_READ,
            Permission.ALERT_RULE_UPDATE, Permission.ALERT_RULE_DELETE,
            Permission.ALERT_LIST, Permission.ALERT_EXPORT,
            Permission.RELAY_CONTROL, Permission.RELAY_READ,
            Permission.AI_PREDICT, Permission.AI_ANOMALY, Permission.AI_RISK,
            Permission.AI_RETRAIN, Permission.AI_REPORT,
            Permission.REPORT_CREATE, Permission.REPORT_READ,
            Permission.REPORT_DOWNLOAD, Permission.REPORT_DELETE,
            Permission.REPORT_LIST,
            Permission.AUDIT_READ, Permission.AUDIT_VERIFY,
            Permission.SYSTEM_HEALTH, Permission.SYSTEM_CONFIG,
        },
        zone_access=None,  # All zones
    ),
    ROLE_OPERATOR: RolePermissions(
        role=ROLE_OPERATOR,
        permissions={
            Permission.USER_READ, Permission.USER_LIST,
            Permission.ZONE_READ, Permission.ZONE_LIST,
            Permission.DEVICE_READ, Permission.DEVICE_LIST,
            Permission.MEASUREMENT_READ, Permission.MEASUREMENT_AGGREGATE,
            Permission.MEASUREMENT_EXPORT,
            Permission.ALERT_READ, Permission.ALERT_ACKNOWLEDGE, Permission.ALERT_RESOLVE,
            Permission.ALERT_RULE_READ, Permission.ALERT_LIST, Permission.ALERT_EXPORT,
            Permission.RELAY_CONTROL, Permission.RELAY_READ,
            Permission.AI_PREDICT, Permission.AI_ANOMALY, Permission.AI_RISK,
            Permission.AI_REPORT,
            Permission.REPORT_CREATE, Permission.REPORT_READ,
            Permission.REPORT_DOWNLOAD, Permission.REPORT_LIST,
            Permission.AUDIT_READ,
            Permission.SYSTEM_HEALTH,
        },
        zone_access=None,  # All zones
    ),
    ROLE_MAINTENANCE: RolePermissions(
        role=ROLE_MAINTENANCE,
        permissions={
            Permission.ZONE_READ, Permission.ZONE_LIST,
            Permission.DEVICE_READ, Permission.DEVICE_LIST,
            Permission.MEASUREMENT_READ, Permission.MEASUREMENT_AGGREGATE,
            Permission.ALERT_READ, Permission.ALERT_ACKNOWLEDGE,
            Permission.ALERT_RULE_READ, Permission.ALERT_LIST,
            Permission.RELAY_CONTROL, Permission.RELAY_READ,
            Permission.AI_RISK,
            Permission.REPORT_READ, Permission.REPORT_DOWNLOAD,
            Permission.SYSTEM_HEALTH,
        },
        zone_access=None,  # All zones
    ),
    ROLE_ANALYST: RolePermissions(
        role=ROLE_ANALYST,
        permissions={
            Permission.ZONE_READ, Permission.ZONE_LIST,
            Permission.DEVICE_READ, Permission.DEVICE_LIST,
            Permission.MEASUREMENT_READ, Permission.MEASUREMENT_AGGREGATE,
            Permission.MEASUREMENT_EXPORT,
            Permission.ALERT_READ, Permission.ALERT_LIST, Permission.ALERT_EXPORT,
            Permission.ALERT_RULE_READ,
            Permission.AI_PREDICT, Permission.AI_ANOMALY, Permission.AI_RISK,
            Permission.AI_REPORT,
            Permission.REPORT_CREATE, Permission.REPORT_READ,
            Permission.REPORT_DOWNLOAD, Permission.REPORT_LIST,
            Permission.AUDIT_READ,
            Permission.SYSTEM_HEALTH,
        },
        zone_access=None,  # All zones
    ),
}


class RBACService:
    """Role-based access control service."""
    
    def __init__(self):
        self.role_permissions = ROLE_PERMISSIONS_MAP
    
    def get_permissions(self, role: str) -> RolePermissions:
        """Get permissions for a role."""
        return self.role_permissions.get(role, RolePermissions(role=role))
    
    def has_permission(self, role: str, permission: Permission) -> bool:
        """Check if role has a specific permission."""
        perms = self.get_permissions(role)
        return perms.has_permission(permission)
    
    def has_zone_access(self, role: str, zone_id: str) -> bool:
        """Check if role has access to a zone."""
        perms = self.get_permissions(role)
        return perms.has_zone_access(zone_id)
    
    def check_permission(self, role: str, permission: Permission, zone_id: str = None) -> bool:
        """Check permission and optional zone access."""
        if not self.has_permission(role, permission):
            return False
        if zone_id and not self.has_zone_access(role, zone_id):
            return False
        return True
    
    def get_user_permissions(self, role: str) -> List[str]:
        """Get list of permission strings for a role."""
        perms = self.get_permissions(role)
        return [p.value for p in perms.permissions]
    
    def require_permission(self, role: str, permission: Permission, zone_id: str = None) -> None:
        """Raise exception if permission not granted."""
        if not self.check_permission(role, permission, zone_id):
            zone_msg = f" in zone {zone_id}" if zone_id else ""
            raise PermissionError(f"Role {role} lacks permission {permission.value}{zone_msg}")
    
    def filter_zones(self, role: str, zone_ids: List[str]) -> List[str]:
        """Filter zone list to only accessible zones."""
        perms = self.get_permissions(role)
        if perms.zone_access is None:
            return zone_ids
        return [z for z in zone_ids if z in perms.zone_access]


# Permission dependency for FastAPI
from functools import wraps
from fastapi import HTTPException, status, Depends
from app.services.auth import get_auth_service, TokenData


_rbac_service: Optional[RBACService] = None


def get_rbac_service() -> RBACService:
    """Get singleton RBACService instance."""
    global _rbac_service
    if _rbac_service is None:
        _rbac_service = RBACService()
    return _rbac_service


def require_permission(permission: Permission, zone_param: str = None):
    """
    FastAPI dependency to require a permission.
    
    Args:
        permission: Required permission
        zone_param: Name of path parameter containing zone_id (optional)
    """
    def dependency(
        token_data: TokenData = Depends(get_auth_service().verify_token),
        rbac: RBACService = Depends(get_rbac_service),
        # Zone ID will be injected by route if zone_param is specified
    ):
        zone_id = None
        # Note: zone_id extraction from path params requires the actual request
        # This is a simplified version; routes should use check_permission_with_zone
        if not rbac.has_permission(token_data.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required"
            )
        return token_data
    return dependency


def check_permission_with_zone(
    token_data: TokenData,
    permission: Permission,
    zone_id: str,
    rbac: RBACService = None
) -> bool:
    """Check permission with zone access (for use in route handlers)."""
    if rbac is None:
        rbac = get_rbac_service()
    return rbac.check_permission(token_data.role, permission, zone_id)


def require_permission_with_zone(permission: Permission, zone_id: str):
    """
    FastAPI dependency factory for permission + zone check.
    Usage: Depends(require_permission_with_zone(Permission.ALERT_READ, zone_id="prod-01"))
    """
    def dependency(
        token_data: TokenData = Depends(get_auth_service().verify_token),
        rbac: RBACService = Depends(get_rbac_service),
    ):
        if not rbac.check_permission(token_data.role, permission, zone_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required for zone {zone_id}"
            )
        return token_data
    return dependency


# Common permission dependencies
def require_admin():
    return require_permission(Permission.USER_CREATE)


def require_operator_or_admin():
    def dependency(token_data: TokenData = Depends(get_auth_service().verify_token)):
        if token_data.role not in (ROLE_ADMIN, ROLE_OPERATOR):
            raise HTTPException(status_code=403, detail="Operator or admin required")
        return token_data
    return dependency


def require_zone_access(zone_id: str):
    def dependency(
        token_data: TokenData = Depends(get_auth_service().verify_token),
        rbac: RBACService = Depends(get_rbac_service),
    ):
        if not rbac.has_zone_access(token_data.role, zone_id):
            raise HTTPException(status_code=403, detail=f"No access to zone {zone_id}")
        return token_data
    return dependency