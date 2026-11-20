"""
API Integration Tests
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from app.main import app


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service") as mock_mqtt, \
             patch("app.main.get_websocket_manager") as mock_ws:
            
            mock_mqtt.return_value.start = AsyncMock()
            mock_mqtt.return_value.stop = AsyncMock()
            mock_mqtt.return_value.get_stats = MagicMock(return_value={"connected": True})
            
            mock_ws.return_value.start = AsyncMock()
            mock_ws.return_value.stop = AsyncMock()
            mock_ws.return_value.get_stats = MagicMock(return_value={})
            
            with TestClient(app) as client:
                yield client
    
    def test_health_check(self, client):
        """Test basic health check."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert "version" in data
    
    def test_readiness_check(self, client):
        """Test readiness probe."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
    
    def test_liveness_check(self, client):
        """Test liveness probe."""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


class TestAuthEndpoints:
    """Test authentication endpoints."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service"), \
             patch("app.main.get_websocket_manager"), \
             patch("app.services.auth.get_database") as mock_db:
            
            # Mock user lookup
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value={
                "_id": "user123",
                "username": "admin",
                "email": "admin@test.com",
                "full_name": "Admin User",
                "role": "admin",
                "is_active": True,
                "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S",  # Admin123!
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_login": None,
            })
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            with TestClient(app) as client:
                yield client
    
    def test_login_success(self, client):
        """Test successful login."""
        response = client.post(
            "/auth/login",
            data={"username": "admin", "password": "Admin123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        # Check refresh token cookie
        assert "refresh_token" in response.cookies
    
    def test_login_failure(self, client):
        """Test failed login."""
        response = client.post(
            "/auth/login",
            data={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == 401
    
    def test_get_me(self, client):
        """Test get current user."""
        # First login
        login_response = client.post(
            "/auth/login",
            data={"username": "admin", "password": "Admin123!"},
        )
        access_token = login_response.json()["access_token"]
        
        # Get user info
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"
        assert "password_hash" not in data


class TestMeasurementsEndpoints:
    """Test measurement endpoints."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service"), \
             patch("app.main.get_websocket_manager"), \
             patch("app.core.database.get_database") as mock_db:
            
            # Mock measurements query
            mock_collection = AsyncMock()
            mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = AsyncMock(__aiter__=AsyncMock(return_value=iter([])))
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            # Mock auth
            with patch("app.main.get_auth_service") as mock_auth:
                mock_auth.return_value.verify_token.return_value = MagicMock(
                    user_id="user123", username="test", role="operator"
                )
                
                with TestClient(app) as client:
                    yield client
    
    def test_get_measurements_missing_params(self, client):
        """Test measurements endpoint requires zone_id and parameter."""
        response = client.get("/measurements", headers={"Authorization": "Bearer fake"})
        assert response.status_code == 422  # Missing required query params
    
    def test_get_measurements_invalid_parameter(self, client):
        """Test invalid parameter is rejected."""
        response = client.get(
            "/measurements",
            params={"zone_id": "prod-01", "parameter": "invalid", "start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 400
    
    def test_get_measurements_valid(self, client):
        """Test valid measurements request."""
        response = client.get(
            "/measurements",
            params={
                "zone_id": "prod-01",
                "parameter": "temperature",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-02T00:00:00",
            },
            headers={"Authorization": "Bearer fake"},
        )
        # Should not be validation error
        assert response.status_code != 422


class TestAlertsEndpoints:
    """Test alerts endpoints."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service"), \
             patch("app.main.get_websocket_manager"), \
             patch("app.core.database.get_database") as mock_db:
            
            mock_collection = AsyncMock()
            mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = AsyncMock(__aiter__=AsyncMock(return_value=iter([])))
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            with patch("app.main.get_auth_service") as mock_auth:
                mock_auth.return_value.verify_token.return_value = MagicMock(
                    user_id="user123", username="test", role="operator"
                )
                
                with TestClient(app) as client:
                    yield client
    
    def test_get_alerts_summary(self, client):
        """Test alert summary endpoint."""
        response = client.get("/alerts/summary", headers={"Authorization": "Bearer fake"})
        assert response.status_code == 200
        data = response.json()
        assert "total_open" in data
        assert "by_level" in data
        assert "by_zone" in data
    
    def test_get_active_alerts(self, client):
        """Test active alerts endpoint."""
        response = client.get("/alerts/active", headers={"Authorization": "Bearer fake"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestAlertRulesEndpoints:
    """Test alert rules endpoints."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service"), \
             patch("app.main.get_websocket_manager"), \
             patch("app.core.database.get_database") as mock_db:
            
            mock_collection = AsyncMock()
            mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = AsyncMock(__aiter__=AsyncMock(return_value=iter([])))
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            with patch("app.main.get_auth_service") as mock_auth:
                mock_auth.return_value.verify_token.return_value = MagicMock(
                    user_id="user123", username="test", role="operator"
                )
                
                with TestClient(app) as client:
                    yield client
    
    def test_list_alert_rules(self, client):
        """Test listing alert rules."""
        response = client.get("/alert-rules", headers={"Authorization": "Bearer fake"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestRelayEndpoints:
    """Test relay control endpoints."""
    
    @pytest.fixture
    def client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service") as mock_mqtt, \
             patch("app.main.get_websocket_manager"), \
             patch("app.core.database.get_database") as mock_db:
            
            mock_mqtt.return_value.publish_relay_command = AsyncMock(return_value=True)
            
            mock_collection = AsyncMock()
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            with patch("app.main.get_auth_service") as mock_auth:
                mock_auth.return_value.verify_token.return_value = MagicMock(
                    user_id="user123", username="test", role="operator"
                )
                
                with TestClient(app) as client:
                    yield client
    
    def test_control_relay_success(self, client):
        """Test successful relay control."""
        response = client.post(
            "/relay/prod-01/1",
            params={"command": "on"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["command"] == "on"
    
    def test_control_relay_invalid_zone(self, client):
        """Test invalid zone."""
        response = client.post(
            "/relay/invalid-zone/1",
            params={"command": "on"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 404
    
    def test_control_relay_invalid_relay(self, client):
        """Test invalid relay ID."""
        response = client.post(
            "/relay/prod-01/5",
            params={"command": "on"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 400
    
    def test_control_relay_invalid_command(self, client):
        """Test invalid command."""
        response = client.post(
            "/relay/prod-01/1",
            params={"command": "invalid"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 422  # Validation error


class TestRBACEnforcement:
    """Test RBAC is enforced on endpoints."""
    
    @pytest.fixture
    def admin_client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service"), \
             patch("app.main.get_websocket_manager"), \
             patch("app.services.auth.get_database") as mock_db:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value={
                "_id": "admin123",
                "username": "admin",
                "email": "admin@test.com",
                "full_name": "Admin",
                "role": "admin",
                "is_active": True,
                "password_hash": "$2b$12$hash",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            with TestClient(app) as client:
                yield client
    
    @pytest.fixture
    def analyst_client(self):
        with patch("app.main.init_database"), \
             patch("app.main.get_mqtt_service"), \
             patch("app.main.get_websocket_manager"), \
             patch("app.services.auth.get_database") as mock_db:
            
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value={
                "_id": "analyst123",
                "username": "analyst",
                "email": "analyst@test.com",
                "full_name": "Analyst",
                "role": "analyst",
                "is_active": True,
                "password_hash": "$2b$12$hash",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            with TestClient(app) as client:
                yield client
    
    def test_admin_can_create_user(self, admin_client):
        """Test admin can create users."""
        response = admin_client.post(
            "/users",
            json={
                "username": "newuser",
                "email": "new@test.com",
                "full_name": "New User",
                "role": "operator",
                "password": "Password123!",
            },
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 201
    
    def test_analyst_cannot_create_user(self, analyst_client):
        """Test analyst cannot create users."""
        response = analyst_client.post(
            "/users",
            json={
                "username": "newuser",
                "email": "new@test.com",
                "full_name": "New User",
                "role": "operator",
                "password": "Password123!",
            },
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 403
    
    def test_analyst_can_read_measurements(self, analyst_client):
        """Test analyst can read measurements."""
        response = analyst_client.get(
            "/measurements",
            params={
                "zone_id": "prod-01",
                "parameter": "temperature",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-02T00:00:00",
            },
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code != 403
    
    def test_analyst_cannot_control_relay(self, analyst_client):
        """Test analyst cannot control relay."""
        response = analyst_client.post(
            "/relay/prod-01/1",
            params={"command": "on"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 403
    
    def test_operator_can_control_relay(self, admin_client):
        """Test operator can control relay (admin has all perms)."""
        response = admin_client.post(
            "/relay/prod-01/1",
            params={"command": "on"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 200


# Import datetime for tests
from datetime import datetime, timezone