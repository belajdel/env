"""
Authentication Service
JWT access + refresh tokens, bcrypt password hashing, token revocation.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

import bcrypt
from jose import jwt, JWTError
from pymongo import ASCENDING

from app.core.config import settings
from app.core.database import get_database, Collections
from app.core.logging import get_logger
from app.models.user import (
    User, UserCreate, UserUpdate, UserInDB, UserPublic, 
    Token, TokenPayload, TokenData, ROLE_ADMIN
)

logger = get_logger(__name__)


class TokenBlacklist:
    """In-memory token blacklist with TTL cleanup (use Redis in production)."""
    
    def __init__(self):
        self._blacklist: Dict[str, datetime] = {}  # jti -> expiry
    
    def add(self, jti: str, expiry: datetime) -> None:
        self._blacklist[jti] = expiry
    
    def is_blacklisted(self, jti: str) -> bool:
        if jti in self._blacklist:
            if self._blacklist[jti] > datetime.now(timezone.utc):
                return True
            else:
                del self._blacklist[jti]
        return False
    
    def cleanup(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [jti for jti, exp in self._blacklist.items() if exp <= now]
        for jti in expired:
            del self._blacklist[jti]


_token_blacklist = TokenBlacklist()


class AuthService:
    """Authentication service with JWT and bcrypt."""
    
    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_expire = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        self.refresh_expire = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        self.issuer = settings.JWT_ISSUER
        self.audience = settings.JWT_AUDIENCE
    
    def hash_password(self, password: str) -> str:
        """Hash password with bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    
    def create_access_token(self, user: UserInDB, extra_claims: Dict[str, Any] = None) -> Tuple[str, TokenPayload]:
        """Create JWT access token."""
        now = datetime.now(timezone.utc)
        expire = now + self.access_expire
        jti = str(uuid.uuid4())
        
        payload = TokenPayload(
            sub=str(user.id),
            username=user.username,
            role=user.role,
            exp=int(expire.timestamp()),
            iat=int(now.timestamp()),
            type="access",
            jti=jti,
        )
        
        if extra_claims:
            payload_dict = payload.model_dump()
            payload_dict.update(extra_claims)
            token = jwt.encode(payload_dict, self.secret_key, algorithm=self.algorithm)
        else:
            token = jwt.encode(payload.model_dump(), self.secret_key, algorithm=self.algorithm)
        
        return token, payload
    
    def create_refresh_token(self, user: UserInDB) -> Tuple[str, TokenPayload]:
        """Create JWT refresh token."""
        now = datetime.now(timezone.utc)
        expire = now + self.refresh_expire
        jti = str(uuid.uuid4())
        
        payload = TokenPayload(
            sub=str(user.id),
            username=user.username,
            role=user.role,
            exp=int(expire.timestamp()),
            iat=int(now.timestamp()),
            type="refresh",
            jti=jti,
        )
        
        token = jwt.encode(payload.model_dump(), self.secret_key, algorithm=self.algorithm)
        return token, payload
    
    def decode_token(self, token: str) -> TokenPayload:
        """Decode and validate JWT token."""
        try:
            payload_dict = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
            )
            return TokenPayload(**payload_dict)
        except JWTError as e:
            logger.warning("token_decode_failed", error=str(e))
            raise ValueError("Invalid token") from e
    
    def verify_token(self, token: str) -> TokenData:
        """Verify token and return token data."""
        payload = self.decode_token(token)
        
        # Check blacklist
        if _token_blacklist.is_blacklisted(payload.jti):
            raise ValueError("Token revoked")
        
        return TokenData(
            user_id=payload.sub,
            username=payload.username,
            role=payload.role,
            token_type=payload.type,
            jti=payload.jti,
        )
    
    def revoke_token(self, token: str) -> bool:
        """Revoke a token (add to blacklist)."""
        try:
            payload = self.decode_token(token)
            _token_blacklist.add(payload.jti, datetime.fromtimestamp(payload.exp, tz=timezone.utc))
            return True
        except ValueError:
            return False
    
    async def authenticate(self, username: str, password: str) -> Optional[UserInDB]:
        """Authenticate user with username/email and password."""
        db = get_database()
        user_doc = await db[Collections.USERS].find_one({
            "$or": [{"username": username}, {"email": username}],
            "is_active": True,
        })
        
        if not user_doc:
            logger.warning("auth_user_not_found", username=username)
            return None
        
        user = UserInDB(**user_doc)
        
        if not self.verify_password(password, user.password_hash):
            logger.warning("auth_invalid_password", username=username)
            return None
        
        # Update last login
        await db[Collections.USERS].update_one(
            {"_id": user.id},
            {"$set": {"last_login": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}}
        )
        
        logger.info("auth_success", user_id=str(user.id), username=user.username)
        return user
    
    async def create_user(self, user_create: UserCreate, actor_id: str) -> UserInDB:
        """Create a new user."""
        db = get_database()
        
        # Check uniqueness
        existing = await db[Collections.USERS].find_one({
            "$or": [
                {"username": user_create.username},
                {"email": user_create.email},
            ]
        })
        if existing:
            raise ValueError("Username or email already exists")
        
        # Hash password
        password_hash = self.hash_password(user_create.password)
        
        now = datetime.now(timezone.utc)
        user = UserInDB(
            username=user_create.username,
            email=user_create.email,
            full_name=user_create.full_name,
            role=user_create.role,
            is_active=user_create.is_active,
            password_hash=password_hash,
            created_at=now,
            updated_at=now,
        )
        
        result = await db[Collections.USERS].insert_one(user.model_dump(by_alias=True))
        user.id = result.inserted_id
        
        # Audit log
        from app.services.audit import get_audit_service
        audit = get_audit_service()
        await audit.log(
            actor_id=actor_id,
            action="create_user",
            resource_type="user",
            resource_id=str(user.id),
            details={"username": user.username, "role": user.role},
        )
        
        logger.info("user_created", user_id=str(user.id), username=user.username, actor=actor_id)
        return user
    
    async def get_user(self, user_id: str) -> Optional[UserInDB]:
        """Get user by ID."""
        db = get_database()
        from bson import ObjectId
        try:
            user_doc = await db[Collections.USERS].find_one({"_id": ObjectId(user_id)})
            if user_doc:
                return UserInDB(**user_doc)
        except Exception:
            pass
        return None
    
    async def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        """Get user by username."""
        db = get_database()
        user_doc = await db[Collections.USERS].find_one({"username": username})
        if user_doc:
            return UserInDB(**user_doc)
        return None
    
    async def update_user(self, user_id: str, user_update: UserUpdate, actor_id: str) -> Optional[UserInDB]:
        """Update user."""
        db = get_database()
        from bson import ObjectId
        
        update_data = user_update.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_user(user_id)
        
        if "password" in update_data:
            update_data["password_hash"] = self.hash_password(update_data.pop("password"))
        
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        result = await db[Collections.USERS].find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$set": update_data},
            return_document=True,
        )
        
        if result:
            user = UserInDB(**result)
            # Audit log
            from app.services.audit import get_audit_service
            audit = get_audit_service()
            await audit.log(
                actor_id=actor_id,
                action="update_user",
                resource_type="user",
                resource_id=user_id,
                details=update_data,
            )
            logger.info("user_updated", user_id=user_id, actor=actor_id)
            return user
        return None
    
    async def delete_user(self, user_id: str, actor_id: str) -> bool:
        """Delete user (soft delete by deactivating)."""
        db = get_database()
        from bson import ObjectId
        
        result = await db[Collections.USERS].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}}
        )
        
        if result.modified_count:
            # Audit log
            from app.services.audit import get_audit_service
            audit = get_audit_service()
            await audit.log(
                actor_id=actor_id,
                action="delete_user",
                resource_type="user",
                resource_id=user_id,
                details={},
            )
            logger.info("user_deleted", user_id=user_id, actor=actor_id)
            return True
        return False
    
    async def list_users(self, skip: int = 0, limit: int = 100, role: str = None, is_active: bool = None) -> list[UserPublic]:
        """List users with pagination and filters."""
        db = get_database()
        
        query = {}
        if role:
            query["role"] = role
        if is_active is not None:
            query["is_active"] = is_active
        
        cursor = db[Collections.USERS].find(query).sort("created_at", -1).skip(skip).limit(limit)
        users = []
        async for doc in cursor:
            user = UserInDB(**doc)
            users.append(UserPublic.from_db(user))
        return users
    
    def create_token_pair(self, user: UserInDB) -> Token:
        """Create access and refresh token pair."""
        access_token, access_payload = self.create_access_token(user)
        refresh_token, refresh_payload = self.create_refresh_token(user)
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(self.access_expire.total_seconds()),
        )
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Token]:
        """Create new access token from refresh token."""
        try:
            token_data = self.verify_token(refresh_token)
            if token_data.token_type != "refresh":
                return None
            
            user = await self.get_user(token_data.user_id)
            if not user or not user.is_active:
                return None
            
            # Revoke old refresh token
            self.revoke_token(refresh_token)
            
            # Create new token pair
            return self.create_token_pair(user)
        except ValueError:
            return None
    
    async def logout(self, access_token: str, refresh_token: str = None) -> bool:
        """Logout user by revoking tokens."""
        success = self.revoke_token(access_token)
        if refresh_token:
            success = self.revoke_token(refresh_token) or success
        return success


_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get singleton AuthService instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service