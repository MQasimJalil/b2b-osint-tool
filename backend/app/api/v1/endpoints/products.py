"""
Product management API endpoints.
"""
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ....core.security import get_current_active_user
from ....db.session import get_db
from ....db.mongodb_session import init_db
from ....crud import products as crud, companies as company_crud, users as user_crud
from ....db.repositories import product_repo, company_repo
from ....schemas import product as schemas

router = APIRouter()


@router.get("/", response_model=schemas.ProductList)
async def list_products(
    company_id: Optional[Union[str, int]] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List products from MongoDB with pagination."""
    # Initialize MongoDB
    await init_db()

    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # If company_id is provided, verify ownership and get products from MongoDB
    if company_id:
        domain = None
        
        # Try finding company in SQL first (legacy) if it looks like an int
        if isinstance(company_id, int) or (isinstance(company_id, str) and company_id.isdigit()):
            company = company_crud.get_company(db, int(company_id))
            if company and company.user_id == user.id:
                domain = company.domain
        
        # If not found in SQL or ID is a string, try MongoDB
        if not domain:
            mongo_company = await company_repo.get_company_by_id(str(company_id))
            if mongo_company and mongo_company.user_id == current_user["sub"]:
                domain = mongo_company.domain
            elif mongo_company:
                 # Found but wrong user
                 raise HTTPException(status_code=403, detail="Not authorized to access this company")

        if not domain:
            raise HTTPException(status_code=404, detail="Company not found")

        # Get products from MongoDB by domain
        mongo_products = await product_repo.get_products_by_domain(domain)

        # Convert MongoDB products to dict format for schema
        products = []
        for p in mongo_products[skip:skip+limit]:
            products.append({
                "id": str(p.id) if hasattr(p, 'id') else 0,
                "company_id": str(company_id),
                "product_external_id": p.product_external_id,
                "name": p.name,
                "brand": p.brand,
                "category": p.category,
                "price": p.price,
                "url": p.url,
                "image_url": p.image_url,
                "description": p.description,
                "specs": p.specs,
                "reviews": p.reviews,
                "created_at": p.created_at
            })

        return schemas.ProductList(
            products=products,
            total=len(mongo_products),
            page=skip // limit + 1,
            page_size=limit
        )
    else:
        # If no company_id, return empty list (could extend to fetch all user's products)
        return schemas.ProductList(
            products=[],
            total=0,
            page=1,
            page_size=limit
        )


@router.get("/{product_id}", response_model=schemas.Product)
def get_product(
    product_id: int,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific product."""
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Verify ownership through company
    company = company_crud.get_company(db, product.company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this product")

    return product


@router.post("/", response_model=schemas.Product, status_code=status.HTTP_201_CREATED)
def create_product(
    product: schemas.ProductCreate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new product."""
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify company ownership
    company = company_crud.get_company(db, product.company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to create product for this company")

    return crud.create_product(db, product)


@router.put("/{product_id}", response_model=schemas.Product)
def update_product(
    product_id: int,
    product_update: schemas.ProductUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a product."""
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Verify ownership through company
    company = company_crud.get_company(db, product.company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this product")

    updated = crud.update_product(db, product_id, product_update)
    return updated


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a product."""
    user = user_crud.get_user_by_auth0_id(db, current_user["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    product = crud.get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Verify ownership through company
    company = company_crud.get_company(db, product.company_id)
    if not company or company.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this product")

    crud.delete_product(db, product_id)
