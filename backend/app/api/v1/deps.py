"""
Common dependencies for API endpoints.
Provides reusable dependencies for authentication, database sessions, etc.
"""
from typing import Generator, Dict, Any
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.security import get_current_user, get_current_active_user
from ...db.session import get_db
from ...crud import users as crud_users
from ...db import models


def get_current_user_from_db(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> models.User:
    """
    Get the current user object from database.

    Args:
        current_user: Current user from JWT token
        db: Database session

    Returns:
        User model from database

    Raises:
        HTTPException: If user not found
    """
    # Try to get user by Auth0 ID first
    if auth0_id := current_user.get("auth0_id"):
        user = crud_users.get_user_by_auth0_id(db, auth0_id)
    else:
        # Fallback to user_id for dev mode
        user_id = current_user.get("user_id")
        if user_id:
            user = crud_users.get_user(db, user_id)
        else:
            user = None

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


def get_current_active_user_from_db(
    current_user: models.User = Depends(get_current_user_from_db)
) -> models.User:
    """
    Get the current active user from database.
    Can be extended to check subscription status, etc.

    Args:
        current_user: Current user from database

    Returns:
        Active user model
    """
    # Add additional checks here (e.g., subscription status)
    return current_user
