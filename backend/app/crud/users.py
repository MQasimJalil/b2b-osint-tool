"""
CRUD operations for User model.
"""
from typing import Optional
from sqlalchemy.orm import Session

from ..db import models
from ..schemas import user as schemas


def get_user(db: Session, user_id: int) -> Optional[models.User]:
    """Get user by ID."""
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """Get user by email."""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_auth0_id(db: Session, auth0_id: str) -> Optional[models.User]:
    """Get user by Auth0 ID."""
    return db.query(models.User).filter(models.User.auth0_id == auth0_id).first()


def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """Create a new user."""
    db_user = models.User(
        auth0_id=user.auth0_id,
        email=user.email,
        name=user.name
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate) -> Optional[models.User]:
    """Update user information."""
    db_user = get_user(db, user_id)
    if not db_user:
        return None

    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value)

    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    """Delete a user."""
    db_user = get_user(db, user_id)
    if not db_user:
        return False

    db.delete(db_user)
    db.commit()
    return True


def get_user_subscription(db: Session, user_id: int) -> Optional[models.Subscription]:
    """Get active subscription for a user."""
    return db.query(models.Subscription).filter(
        models.Subscription.user_id == user_id,
        models.Subscription.status == "active"
    ).first()


def create_subscription(db: Session, subscription: schemas.SubscriptionCreate) -> models.Subscription:
    """Create a new subscription."""
    db_subscription = models.Subscription(**subscription.model_dump())
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription
