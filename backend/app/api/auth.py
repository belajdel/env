"""
Authentication API Routes
JWT access + refresh tokens, login, logout, password change.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.core.logging import get_logger
from app.services.auth import get_auth_service, TokenData, Token
from app.services.audit import get_audit_service
from app.models.user import UserCreate, UserPublic, ROLE_ADMIN

router = APIRouter(prefix="/auth", tags=["authentication"])

logger = get_logger(__name__)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/login", response_model=TokenResponse, summary="User login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth=Depends(get_auth_service),
    audit=Depends(get_audit_service),
):
    """Authenticate user and return JWT tokens."""
    user = await auth.authenticate(form_data.username, form_data.password)
    if not user:
        await audit.log(
            actor_id="unknown",
            actor_role="anonymous",
            action="login_failed",
            resource_type="auth",
            resource_id="login",
            details={"username": form_data.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    tokens = auth.create_token_pair(user)
    
    # Set refresh token as HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    
    await audit.log(
        actor_id=str(user.id),
        actor_role=user.role,
        action="login",
        resource_type="auth",
        resource_id="login",
        details={"username": user.username},
    )
    
    logger.info("user_login", user_id=str(user.id), username=user.username)
    
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(
    response: Response,
    request: Request,
    auth=Depends(get_auth_service),
    audit=Depends(get_audit_service),
):
    """Refresh access token using refresh token from cookie or body."""
    # Try to get refresh token from cookie first
    refresh_token = request.cookies.get("refresh_token")
    
    # Fallback to body
    if not refresh_token:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )
    
    tokens = await auth.refresh_access_token(refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    # Update refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", summary="User logout")
async def logout(
    response: Response,
    request: Request,
    auth=Depends(get_auth_service),
    audit=Depends(get_audit_service),
    token_data: TokenData = Depends(get_auth_service().verify_token),
):
    """Logout user and revoke tokens."""
    # Get tokens
    access_token = request.headers.get("Authorization", "").replace("Bearer ", "")
    refresh_token = request.cookies.get("refresh_token")
    
    await auth.logout(access_token, refresh_token)
    
    # Clear refresh token cookie
    response.delete_cookie(key="refresh_token", httponly=True, secure=not settings.DEBUG, samesite="lax")
    
    await audit.log(
        actor_id=token_data.user_id,
        actor_role=token_data.role,
        action="logout",
        resource_type="auth",
        resource_id="logout",
    )
    
    return {"message": "Logged out successfully"}


@router.post("/change-password", summary="Change password")
async def change_password(
    request: ChangePasswordRequest,
    auth=Depends(get_auth_service),
    audit=Depends(get_audit_service),
    token_data: TokenData = Depends(get_auth_service().verify_token),
):
    """Change current user's password."""
    user = await auth.get_user(token_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not auth.verify_password(request.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    new_hash = auth.hash_password(request.new_password)
    
    from app.core.database import get_database, Collections
    from bson import ObjectId
    db = get_database()
    
    await db[Collections.USERS].update_one(
        {"_id": ObjectId(token_data.user_id)},
        {"$set": {"password_hash": new_hash, "updated_at": datetime.now(timezone.utc)}}
    )
    
    # Revoke all tokens (force re-login)
    await auth.logout("", "")  # This will be enhanced to revoke all user tokens
    
    await audit.log(
        actor_id=token_data.user_id,
        actor_role=token_data.role,
        action="change_password",
        resource_type="user",
        resource_id=token_data.user_id,
    )
    
    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserPublic, summary="Get current user")
async def get_current_user(
    token_data: TokenData = Depends(get_auth_service().verify_token),
    auth=Depends(get_auth_service),
):
    """Get current authenticated user info."""
    user = await auth.get_user(token_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic.from_db(user)


# Import datetime for password change
from datetime import datetime, timezone