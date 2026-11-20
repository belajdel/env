"""
RBAC Tests
"""

import pytest
from app.services.rbac import (
    get_rbac_service, RBACService, Permission, RolePermissions,
    ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST
)
from app.models.user import TokenData


class TestRBACService:
    """Test RBAC service."""
    
    @pytest.fixture
    def rbac(self):
        return get_rbac_service()
    
    def test_admin_has_all_permissions(self, rbac):
        """Test admin has all permissions."""
        for perm in Permission:
            assert rbac.has_permission(ROLE_ADMIN, perm), f"Admin missing {perm.value}"
    
    def test_operator_permissions(self, rbac):
        """Test operator permissions."""
        # Should have
        assert rbac.has_permission(ROLE_OPERATOR, Permission.USER_READ)
        assert rbac.has_permission(ROLE_OPERATOR, Permission.ZONE_READ)
        assert rbac.has_permission(ROLE_OPERATOR, Permission.ALERT_ACKNOWLEDGE)
        assert rbac.has_permission(ROLE_OPERATOR, Permission.RELAY_CONTROL)
        assert rbac.has_permission(ROLE_OPERATOR, Permission.AI_PREDICT)
        
        # Should NOT have
        assert not rbac.has_permission(ROLE_OPERATOR, Permission.USER_CREATE)
        assert not rbac.has_permission(ROLE_OPERATOR, Permission.USER_DELETE)
        assert not rbac.has_permission(ROLE_OPERATOR, Permission.AI_RETRAIN)
        assert not rbac.has_permission(ROLE_OPERATOR, Permission.AUDIT_READ)
    
    def test_maintenance_permissions(self, rbac):
        """Test maintenance permissions."""
        # Should have
        assert rbac.has_permission(ROLE_MAINTENANCE, Permission.DEVICE_READ)
        assert rbac.has_permission(ROLE_MAINTENANCE, Permission.RELAY_CONTROL)
        assert rbac.has_permission(ROLE_MAINTENANCE, Permission.ALERT_ACKNOWLEDGE)
        
        # Should NOT have
        assert not rbac.has_permission(ROLE_MAINTENANCE, Permission.USER_READ)
        assert not rbac.has_permission(ROLE_MAINTENANCE, Permission.ZONE_CREATE)
        assert not rbac.has_permission(ROLE_MAINTENANCE, Permission.AI_PREDICT)
        assert not rbac.has_permission(ROLE_MAINTENANCE, Permission.REPORT_CREATE)
    
    def test_analyst_permissions(self, rbac):
        """Test analyst permissions."""
        # Should have
        assert rbac.has_permission(ROLE_ANALYST, Permission.MEASUREMENT_READ)
        assert rbac.has_permission(ROLE_ANALYST, Permission.MEASUREMENT_EXPORT)
        assert rbac.has_permission(ROLE_ANALYST, Permission.AI_PREDICT)
        assert rbac.has_permission(ROLE_ANALYST, Permission.AI_ANOMALY)
        assert rbac.has_permission(ROLE_ANALYST, Permission.REPORT_CREATE)
        
        # Should NOT have
        assert not rbac.has_permission(ROLE_ANALYST, Permission.RELAY_CONTROL)
        assert not rbac.has_permission(ROLE_ANALYST, Permission.ALERT_ACKNOWLEDGE)
        assert not rbac.has_permission(ROLE_ANALYST, Permission.USER_CREATE)
        assert not rbac.has_permission(ROLE_ANALYST, Permission.AI_RETRAIN)
    
    def test_zone_access_all_roles(self, rbac):
        """Test all roles have access to all zones by default."""
        zones = ["prod-01", "prod-02", "store-01", "tech-01"]
        
        for role in [ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST]:
            for zone in zones:
                assert rbac.has_zone_access(role, zone), f"{role} denied access to {zone}"
    
    def test_check_permission_with_zone(self, rbac):
        """Test check_permission with zone."""
        # Admin should have access to all zones
        assert rbac.check_permission(ROLE_ADMIN, Permission.USER_CREATE, "prod-01")
        assert rbac.check_permission(ROLE_ADMIN, Permission.RELAY_CONTROL, "tech-02")
        
        # Operator should have relay control on all zones
        assert rbac.check_permission(ROLE_OPERATOR, Permission.RELAY_CONTROL, "prod-01")
        
        # Maintenance should have relay control
        assert rbac.check_permission(ROLE_MAINTENANCE, Permission.RELAY_CONTROL, "tech-01")
        
        # Analyst should NOT have relay control
        assert not rbac.check_permission(ROLE_ANALYST, Permission.RELAY_CONTROL, "prod-01")
    
    def test_require_permission_raises(self, rbac):
        """Test require_permission raises on denied."""
        with pytest.raises(PermissionError):
            rbac.require_permission(ROLE_OPERATOR, Permission.USER_CREATE)
        
        with pytest.raises(PermissionError):
            rbac.require_permission(ROLE_ANALYST, Permission.RELAY_CONTROL, "prod-01")
    
    def test_get_user_permissions(self, rbac):
        """Test getting permission list for role."""
        admin_perms = rbac.get_user_permissions(ROLE_ADMIN)
        assert len(admin_perms) == len(Permission)
        
        operator_perms = rbac.get_user_permissions(ROLE_OPERATOR)
        assert "user:read" in operator_perms
        assert "user:create" not in operator_perms
        assert "relay:control" in operator_perms
    
    def test_filter_zones(self, rbac):
        """Test zone filtering."""
        all_zones = ["prod-01", "prod-02", "store-01", "tech-01"]
        
        # All roles get all zones by default
        for role in [ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST]:
            filtered = rbac.filter_zones(role, all_zones)
            assert filtered == all_zones


class TestTokenData:
    """Test TokenData model."""
    
    def test_token_data_creation(self):
        """Test creating TokenData."""
        from app.services.auth import TokenData
        
        token_data = TokenData(
            user_id="123",
            username="testuser",
            role="admin",
            token_type="access",
            jti="abc123",
        )
        
        assert token_data.user_id == "123"
        assert token_data.username == "testuser"
        assert token_data.role == "admin"
        assert token_data.token_type == "access"
        assert token_data.jti == "abc123"