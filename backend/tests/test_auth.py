"""
Authentication Tests
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.auth import get_auth_service, _token_blacklist
from app.models.user import UserInDB, UserCreate, TokenPayload, TokenData, ROLE_ADMIN
from app.core.config import Settings


class TestAuthService:
    """Test authentication service."""
    
    @pytest.fixture
    def auth_service(self):
        """Auth service with test settings."""
        with patch("app.services.auth.settings", Settings(
            JWT_SECRET_KEY="test-secret",
            JWT_ALGORITHM="HS256",
            JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30,
            JWT_REFRESH_TOKEN_EXPIRE_DAYS=7,
            JWT_ISSUER="test",
            JWT_AUDIENCE="test",
        )):
            service = get_auth_service()
            # Clear blacklist
            _token_blacklist._blacklist.clear()
            return service
    
    @pytest.fixture
    def test_user(self):
        """Test user."""
        return UserInDB(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            role=ROLE_ADMIN,
            is_active=True,
            password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S",  # "Admin123!"
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    
    def test_hash_password(self, auth_service):
        """Test password hashing."""
        password = "TestPass123!"
        hash1 = auth_service.hash_password(password)
        hash2 = auth_service.hash_password(password)
        
        # Hashes should be different (bcrypt uses salt)
        assert hash1 != hash2
        # But both should verify
        assert auth_service.verify_password(password, hash1)
        assert auth_service.verify_password(password, hash2)
        # Wrong password should fail
        assert not auth_service.verify_password("WrongPass", hash1)
    
    def test_create_access_token(self, auth_service, test_user):
        """Test access token creation."""
        token, payload = auth_service.create_access_token(test_user)
        
        assert isinstance(token, str)
        assert len(token) > 0
        assert payload.sub == str(test_user.id)
        assert payload.username == test_user.username
        assert payload.role == test_user.role
        assert payload.type == "access"
        assert payload.exp > payload.iat
    
    def test_create_refresh_token(self, auth_service, test_user):
        """Test refresh token creation."""
        token, payload = auth_service.create_refresh_token(test_user)
        
        assert isinstance(token, str)
        assert payload.type == "refresh"
        assert payload.exp - payload.iat == 7 * 24 * 60 * 60  # 7 days
    
    def test_decode_valid_token(self, auth_service, test_user):
        """Test decoding valid token."""
        token, _ = auth_service.create_access_token(test_user)
        payload = auth_service.decode_token(token)
        
        assert payload.sub == str(test_user.id)
        assert payload.username == test_user.username
    
    def test_decode_invalid_token(self, auth_service):
        """Test decoding invalid token."""
        with pytest.raises(ValueError, match="Invalid token"):
            auth_service.decode_token("invalid.token.here")
    
    def test_decode_expired_token(self, auth_service, test_user):
        """Test decoding expired token."""
        # Create token with past expiry
        with patch("app.services.auth.datetime") as mock_datetime:
            past = datetime.now(timezone.utc) - timedelta(hours=1)
            mock_datetime.now.return_value = past
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            token, _ = auth_service.create_access_token(test_user)
        
        with pytest.raises(ValueError, match="Invalid token"):
            auth_service.decode_token(token)
    
    def test_token_blacklist(self, auth_service, test_user):
        """Test token revocation."""
        access_token, access_payload = auth_service.create_access_token(test_user)
        refresh_token, refresh_payload = auth_service.create_refresh_token(test_user)
        
        # Tokens should be valid initially
        assert auth_service.verify_token(access_token).user_id == str(test_user.id)
        assert auth_service.verify_token(refresh_token).user_id == str(test_user.id)
        
        # Revoke access token
        assert auth_service.revoke_token(access_token)
        
        # Access token should now be invalid
        with pytest.raises(ValueError, match="Token revoked"):
            auth_service.verify_token(access_token)
        
        # Refresh token should still be valid
        assert auth_service.verify_token(refresh_token).user_id == str(test_user.id)
    
    def test_create_token_pair(self, auth_service, test_user):
        """Test token pair creation."""
        tokens = auth_service.create_token_pair(test_user)
        
        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"
        assert tokens.expires_in == 30 * 60  # 30 minutes
    
    @pytest.mark.asyncio
    async def test_refresh_access_token(self, auth_service, test_user):
        """Test refreshing access token."""
        refresh_token, _ = auth_service.create_refresh_token(test_user)
        
        # Mock database get_user
        with patch("app.services.auth.get_database") as mock_db:
            mock_collection = AsyncMock()
            mock_collection.find_one = AsyncMock(return_value=test_user.model_dump(by_alias=True))
            mock_db.return_value = MagicMock()
            mock_db.return_value.__getitem__ = MagicMock(return_value=mock_collection)
            
            new_tokens = await auth_service.refresh_access_token(refresh_token)
            
            assert new_tokens is not None
            assert new_tokens.access_token
            assert new_tokens.refresh_token
            # Old refresh token should be revoked
            with pytest.raises(ValueError):
                auth_service.verify_token(refresh_token)
    
    @pytest.mark.asyncio
    async def test_logout(self, auth_service, test_user):
        """Test logout."""
        access_token, _ = auth_service.create_access_token(test_user)
        refresh_token, _ = auth_service.create_refresh_token(test_user)
        
        result = await auth_service.logout(access_token, refresh_token)
        
        assert result is True
        # Both tokens should be revoked
        with pytest.raises(ValueError):
            auth_service.verify_token(access_token)
        with pytest.raises(ValueError):
            auth_service.verify_token(refresh_token)