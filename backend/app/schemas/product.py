"""
Pydantic schemas for Product model.
Used for request/response validation and serialization.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any, Union
from datetime import datetime


class ProductBase(BaseModel):
    """Base product schema."""
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    reviews: Optional[List[Union[str, Dict[str, Any]]]] = None  # Accept both strings and dicts


class ProductCreate(ProductBase):
    """Schema for creating a product."""
    company_id: Union[str, int]
    product_external_id: Optional[str] = None


class ProductUpdate(BaseModel):
    """Schema for updating a product."""
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    reviews: Optional[List[Union[str, Dict[str, Any]]]] = None  # Accept both strings and dicts


class Product(ProductBase):
    """Schema for product in API responses."""
    id: Union[str, int, None] = None
    company_id: Union[str, int, None] = None
    product_external_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductList(BaseModel):
    """Schema for paginated product list."""
    products: List[Product]
    total: int
    page: int
    page_size: int
