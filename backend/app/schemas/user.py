"""
Pydantic schemas for User model.
Used for request/response validation and serialization.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """Base user schema with common attributes."""
    email: EmailStr
    name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user."""
    auth0_id: str


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None


class UserInDB(UserBase):
    """Schema for user as stored in database."""
    id: int
    auth0_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class User(UserInDB):
    """Schema for user in API responses."""
    pass


class SubscriptionBase(BaseModel):
    """Base subscription schema."""
    plan: str
    status: str


class SubscriptionCreate(SubscriptionBase):
    """Schema for creating a subscription."""
    user_id: int
    stripe_subscription_id: Optional[str] = None


class SubscriptionUpdate(BaseModel):
    """Schema for updating a subscription."""
    plan: Optional[str] = None
    status: Optional[str] = None


class Subscription(SubscriptionBase):
    """Schema for subscription in API responses."""
    id: int
    user_id: int
    stripe_subscription_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
