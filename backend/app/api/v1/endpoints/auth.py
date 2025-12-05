"""
Authentication endpoints for both development and production.
Provides JWT token generation, Auth0 integration, and user management.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import timedelta
from sqlalchemy.orm import Session

from ....core.security import create_access_token, verify_auth0_token, get_current_user
from ....core.config import get_settings
from ....db.session import get_db
from ....crud import users as crud_users
from ....schemas.user import UserCreate, User as UserResponse
from ....core.exceptions import AuthenticationError, ResourceNotFound, ResourceAlreadyExists

settings = get_settings()
router = APIRouter()


class DevLoginRequest(BaseModel):
    """Request model for dev login."""
    email: Optional[EmailStr] = "dev@local.com"
    username: Optional[str] = "Dev User"


class TokenResponse(BaseModel):
    """Response model for token."""
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(request: DevLoginRequest = DevLoginRequest()):
    """
    Development-only login endpoint that generates JWT tokens.

    This endpoint is meant for local development only and should be disabled
    in production environments.

    Args:
        request: Login request with optional email and username

    Returns:
        TokenResponse with access token and user info

    Raises:
        HTTPException: If not in debug mode
    """
    # Only allow in debug/development mode
    if not settings.DEBUG and settings.ENVIRONMENT != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login is only available in development mode"
        )

    # Create mock user data
    user_data = {
        "sub": "dev-user-1",
        "user_id": 1,
        "email": request.email,
        "username": request.username or "Dev User",
        "is_active": True,
        "subscription_tier": "enterprise",  # Give full access in dev mode
        "dev_mode": True
    }

    # Generate JWT token
    access_token = create_access_token(
        data=user_data,
        expires_delta=timedelta(days=7)  # Long expiry for dev convenience
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_data
    )


@router.get("/test")
async def test_auth():
    """
    Simple test endpoint to verify auth router is working.
    Does not require authentication.
    """
    return {
        "message": "Auth router is working",
        "debug_mode": settings.DEBUG,
        "environment": settings.ENVIRONMENT
    }


# ============================================================================
# Production Auth0 Integration Endpoints
# ============================================================================

class LoginRequest(BaseModel):
    """Request model for Auth0 login."""
    auth0_token: str


class LoginResponse(BaseModel):
    """Response model for login."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: UserResponse


class SignupRequest(BaseModel):
    """Request model for signup."""
    auth0_token: str
    name: Optional[str] = None


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Exchange Auth0 token for application JWT token.

    This endpoint verifies the Auth0 token and either:
    1. Returns an existing user with a new JWT, or
    2. Automatically creates a user if they don't exist (auto-registration)

    Args:
        request: Login request with Auth0 token
        db: Database session

    Returns:
        LoginResponse with JWT access token and user info

    Raises:
        HTTPException: If Auth0 token is invalid
    """
    try:
        # Verify Auth0 token
        auth0_payload = await verify_auth0_token(request.auth0_token)

        # Extract user info from Auth0 token
        auth0_id = auth0_payload.get("sub")
        email = auth0_payload.get("email")
        name = auth0_payload.get("name") or auth0_payload.get("nickname")

        if not auth0_id or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Auth0 token: missing sub or email"
            )

        # Check if user exists
        user = crud_users.get_user_by_auth0_id(db, auth0_id)

        # Auto-create user if doesn't exist (auto-registration)
        if not user:
            user_create = UserCreate(
                auth0_id=auth0_id,
                email=email,
                name=name
            )
            user = crud_users.create_user(db, user_create)

        # Create application JWT token
        token_data = {
            "sub": str(user.id),
            "user_id": user.id,
            "auth0_id": user.auth0_id,
            "email": user.email,
            "name": user.name
        }

        access_token = create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Convert user to response schema
        user_response = UserResponse.model_validate(user)

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=user_response
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )


@router.post("/signup", response_model=LoginResponse)
async def signup(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new user account with Auth0 token.

    Similar to login, but explicitly for new user registration.
    If user already exists, returns 409 Conflict.

    Args:
        request: Signup request with Auth0 token
        db: Database session

    Returns:
        LoginResponse with JWT access token and user info

    Raises:
        HTTPException: If user already exists or Auth0 token is invalid
    """
    try:
        # Verify Auth0 token
        auth0_payload = await verify_auth0_token(request.auth0_token)

        # Extract user info
        auth0_id = auth0_payload.get("sub")
        email = auth0_payload.get("email")
        name = request.name or auth0_payload.get("name") or auth0_payload.get("nickname")

        if not auth0_id or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Auth0 token: missing sub or email"
            )

        # Check if user already exists
        existing_user = crud_users.get_user_by_auth0_id(db, auth0_id)
        if existing_user:
            raise ResourceAlreadyExists("User", auth0_id)

        # Create new user
        user_create = UserCreate(
            auth0_id=auth0_id,
            email=email,
            name=name
        )
        user = crud_users.create_user(db, user_create)

        # Create JWT token
        token_data = {
            "sub": str(user.id),
            "user_id": user.id,
            "auth0_id": user.auth0_id,
            "email": user.email,
            "name": user.name
        }

        access_token = create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # Convert user to response schema
        user_response = UserResponse.model_validate(user)

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=user_response
        )

    except ResourceAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Signup failed: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current authenticated user information.

    Requires valid JWT token in Authorization header.

    Args:
        current_user: Current user from JWT token
        db: Database session

    Returns:
        Current user information

    Raises:
        HTTPException: If user not found
    """
    # Get user from database
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user = crud_users.get_user(db, user_id)
    if not user:
        raise ResourceNotFound("User", str(user_id))

    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Refresh JWT access token.

    Requires valid (possibly expired) JWT token.
    Returns a new token with extended expiration.

    Args:
        current_user: Current user from JWT token
        db: Database session

    Returns:
        New JWT access token
    """
    # Get fresh user data from database
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user = crud_users.get_user(db, user_id)
    if not user:
        raise ResourceNotFound("User", str(user_id))

    # Create new token with fresh data
    token_data = {
        "sub": str(user.id),
        "user_id": user.id,
        "auth0_id": user.auth0_id,
        "email": user.email,
        "name": user.name
    }

    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    user_response = UserResponse.model_validate(user)

    return TokenResponse(
        access_token=access_token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "auth0_id": user.auth0_id
        }
    )


@router.post("/logout")
async def logout():
    """
    Logout endpoint (client-side token invalidation).

    Since we're using stateless JWT tokens, actual logout happens client-side
    by removing the token from storage. This endpoint exists for completeness
    and can be enhanced with token blacklisting if needed.

    Returns:
        Success message
    """
    return {
        "message": "Logged out successfully",
        "detail": "Please remove the token from client storage"
    }
