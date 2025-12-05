"""
Product Repository

CRUD operations for Product documents.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from beanie import PydanticObjectId

from ..mongodb_models import Product


async def get_product_by_id(product_id: str) -> Optional[Product]:
    """Get product by ID"""
    try:
        return await Product.get(PydanticObjectId(product_id))
    except Exception:
        return None


async def get_products_by_company(
    company_id: str,
    skip: int = 0,
    limit: int = 100
) -> List[Product]:
    """Get all products for a company"""
    return await Product.find(
        Product.company_id == company_id
    ).skip(skip).limit(limit).to_list()


async def get_products_by_domain(
    domain: str,
    skip: int = 0,
    limit: int = 100
) -> List[Product]:
    """Get all products for a domain"""
    return await Product.find(
        Product.domain == domain
    ).skip(skip).limit(limit).to_list()


async def create_product(product_data: Dict[str, Any]) -> Product:
    """Create a new product"""
    product = Product(**product_data)
    await product.insert()
    return product


async def create_products_bulk(products_data: List[Dict[str, Any]]) -> List[Product]:
    """Create multiple products at once"""
    products = [Product(**data) for data in products_data]
    await Product.insert_many(products)
    return products


async def delete_products_by_domain(domain: str) -> int:
    """Delete all products for a domain"""
    result = await Product.find(Product.domain == domain).delete()
    return result.deleted_count


async def count_products_by_domain(domain: str) -> int:
    """Count products for a domain"""
    return await Product.find(Product.domain == domain).count()


async def search_products(
    domain: str,
    search_query: str,
    skip: int = 0,
    limit: int = 100
) -> List[Product]:
    """Search products by name, brand, or category"""
    import re
    regex = re.compile(search_query, re.IGNORECASE)

    products = await Product.find(
        Product.domain == domain,
        {
            "$or": [
                {"name": regex},
                {"brand": regex},
                {"category": regex},
                {"description": regex}
            ]
        }
    ).skip(skip).limit(limit).to_list()

    return products
