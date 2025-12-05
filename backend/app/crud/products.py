"""
CRUD operations for Product model.
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from ..db import models
from ..schemas import product as schemas


def get_product(db: Session, product_id: int) -> Optional[models.Product]:
    """Get product by ID."""
    return db.query(models.Product).filter(models.Product.id == product_id).first()


def get_products(db: Session, company_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[models.Product]:
    """Get products with pagination."""
    query = db.query(models.Product)
    if company_id:
        query = query.filter(models.Product.company_id == company_id)
    return query.offset(skip).limit(limit).all()


def get_products_count(db: Session, company_id: Optional[int] = None) -> int:
    """Get total count of products."""
    query = db.query(models.Product)
    if company_id:
        query = query.filter(models.Product.company_id == company_id)
    return query.count()


def create_product(db: Session, product: schemas.ProductCreate) -> models.Product:
    """Create a new product."""
    import json
    db_product = models.Product(
        company_id=product.company_id,
        product_external_id=product.product_external_id,
        name=product.name,
        brand=product.brand,
        category=product.category,
        price=product.price,
        url=product.url,
        image_url=product.image_url,
        description=product.description,
        specs=json.dumps(product.specs) if product.specs else None,
        reviews=json.dumps(product.reviews) if product.reviews else None
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product


def update_product(db: Session, product_id: int, product_update: schemas.ProductUpdate) -> Optional[models.Product]:
    """Update product information."""
    import json
    db_product = get_product(db, product_id)
    if not db_product:
        return None

    update_data = product_update.model_dump(exclude_unset=True)

    # Handle JSON fields
    if "specs" in update_data and update_data["specs"] is not None:
        update_data["specs"] = json.dumps(update_data["specs"])
    if "reviews" in update_data and update_data["reviews"] is not None:
        update_data["reviews"] = json.dumps(update_data["reviews"])

    for field, value in update_data.items():
        setattr(db_product, field, value)

    db.commit()
    db.refresh(db_product)
    return db_product


def delete_product(db: Session, product_id: int) -> bool:
    """Delete a product."""
    db_product = get_product(db, product_id)
    if not db_product:
        return False

    db.delete(db_product)
    db.commit()
    return True


def bulk_create_products(db: Session, products: List[schemas.ProductCreate]) -> List[models.Product]:
    """Bulk create products."""
    import json
    db_products = []
    for product in products:
        db_product = models.Product(
            company_id=product.company_id,
            product_external_id=product.product_external_id,
            name=product.name,
            brand=product.brand,
            category=product.category,
            price=product.price,
            url=product.url,
            image_url=product.image_url,
            description=product.description,
            specs=json.dumps(product.specs) if product.specs else None,
            reviews=json.dumps(product.reviews) if product.reviews else None
        )
        db_products.append(db_product)

    db.bulk_save_objects(db_products)
    db.commit()
    return db_products
