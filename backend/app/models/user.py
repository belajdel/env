"""
User and Authentication Models
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, EmailStr, field_validator
from bson import ObjectId


class PyObjectId(ObjectId):
    """Custom ObjectId for Pydantic v2."""
    
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return handler(core_schema.str_schema())
    
    @classmethod
    def __get_pydantic_core_schema__(cls, core_schema, handler):
        from pydantic_core import core_schema as pcs
        return pcs.union_schema([
            pcs.is_instance_schema(ObjectId),
            pcs.chain_schema([
                pcs.str_schema(),
                pcs.no_info_plain_validator_function(cls.validate),
            ]),
        ])
    
    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


# Role constants
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_MAINTENANCE = "maintenance"
ROLE_ANALYST = "analyst"
VALID_ROLES = (ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST)


class UserBase(BaseModel):
    """Base user model with common fields."""
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    role: Literal[ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST] = ROLE_OPERATOR
    is_active: bool = True


class UserCreate(UserBase):
    """Model for creating a new user."""
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        # Require at least one uppercase, lowercase, digit, special char
        import re
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class UserUpdate(BaseModel):
    """Model for updating a user (all fields optional)."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[Literal[ROLE_ADMIN, ROLE_OPERATOR, ROLE_MAINTENANCE, ROLE_ANALYST]] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class UserInDB(UserBase):
    """User model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    password_hash: str
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
    }


class UserPublic(UserBase):
    """User model for public API responses (no password)."""
    id: str = Field(..., alias="_id")
    created_at: datetime
    last_login: Optional[datetime] = None
    
    model_config = {
        "populate_by_name": True,
        "json_encoders": {ObjectId: str},
    }
    
    @classmethod
    def from_db(cls, user: UserInDB) -> "UserPublic":
        return cls(
            _id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=user.last_login,
        )


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenPayload(BaseModel):
    """Decoded JWT token payload."""
    sub: str  # user id
    username: str
    role: str
    exp: int
    iat: int
    type: Literal["access", "refresh"] = "access"
    jti: str  # JWT ID for revocation


class TokenData(BaseModel):
    """Token data for dependency injection."""
    user_id: str
    username: str
    role: str
    token_type: str
    jti: str