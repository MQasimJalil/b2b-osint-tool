"""
User management API endpoints.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ....core.security import get_current_active_user
from ....db.session import get_db
from ....crud import users as crud
from ....schemas import user as schemas

router = APIRouter()


@router.get("/me", response_model=schemas.User)
def read_current_user(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get current user information."""
    user = crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """Create a new user."""
    db_user = crud.get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = crud.get_user_by_auth0_id(db, user.auth0_id)
    if db_user:
        raise HTTPException(status_code=400, detail="User already exists")

    return crud.create_user(db, user)


@router.put("/{user_id}", response_model=schemas.User)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user information."""
    # Verify user can only update their own profile
    db_user = crud.get_user_by_auth0_id(db, current_user["sub"])
    if not db_user or db_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this user")

    updated_user = crud.update_user(db, user_id, user_update)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return updated_user


@router.get("/me/subscription", response_model=schemas.Subscription)
def read_current_user_subscription(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get current user's active subscription."""
    user = crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    subscription = crud.get_user_subscription(db, user.id)
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    return subscription
