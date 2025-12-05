"""Pydantic schemas for request/response validation."""
from .user import User, UserCreate, UserUpdate, Subscription, SubscriptionCreate
from .company import (
    Company, CompanyCreate, CompanyUpdate, CompanyWithRelations,
    Contact, ContactCreate, SocialMedia, SocialMediaCreate,
    EnrichmentHistory, EnrichmentHistoryCreate
)
from .product import Product, ProductCreate, ProductUpdate, ProductList
from .email import (
    EmailVerification, EmailDraft, EmailDraftCreate,
    EmailSendRequest, EmailVerifyRequest, EmailVerifyResponse
)

__all__ = [
    # User schemas
    "User", "UserCreate", "UserUpdate", "Subscription", "SubscriptionCreate",
    # Company schemas
    "Company", "CompanyCreate", "CompanyUpdate", "CompanyWithRelations",
    "Contact", "ContactCreate", "SocialMedia", "SocialMediaCreate",
    "EnrichmentHistory", "EnrichmentHistoryCreate",
    # Product schemas
    "Product", "ProductCreate", "ProductUpdate", "ProductList",
    # Email schemas
    "EmailVerification", "EmailDraft", "EmailDraftCreate",
    "EmailSendRequest", "EmailVerifyRequest", "EmailVerifyResponse",
]
