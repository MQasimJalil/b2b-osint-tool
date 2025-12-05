"""
CRUD operations for Company, Contact, and SocialMedia models.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..db import models
from ..schemas import company as schemas


def get_company(db: Session, company_id: int) -> Optional[models.Company]:
    """Get company by ID."""
    return db.query(models.Company).filter(models.Company.id == company_id).first()


def get_company_by_domain(db: Session, domain: str) -> Optional[models.Company]:
    """Get company by domain."""
    return db.query(models.Company).filter(models.Company.domain == domain).first()


def get_companies(db: Session, user_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[models.Company]:
    """Get companies with pagination."""
    query = db.query(models.Company)
    if user_id:
        query = query.filter(models.Company.user_id == user_id)
    return query.offset(skip).limit(limit).all()


def count_companies(db: Session, user_id: Optional[int] = None) -> int:
    """Count total companies for a user."""
    query = db.query(models.Company)
    if user_id:
        query = query.filter(models.Company.user_id == user_id)
    return query.count()


def count_companies_with_contacts(db: Session, user_id: Optional[int] = None) -> int:
    """Count companies that have at least one contact."""
    query = db.query(models.Company).filter(models.Company.contact_score > 0)
    if user_id:
        query = query.filter(models.Company.user_id == user_id)
    return query.count()


def count_total_contacts(db: Session, user_id: Optional[int] = None) -> int:
    """Count total contacts across all companies for a user."""
    query = db.query(models.Contact)
    if user_id:
        query = query.join(models.Company).filter(models.Company.user_id == user_id)
    return query.count()


def search_companies(db: Session, search_term: str, user_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[models.Company]:
    """Search companies by name or domain."""
    query = db.query(models.Company).filter(
        or_(
            models.Company.company_name.ilike(f"%{search_term}%"),
            models.Company.domain.ilike(f"%{search_term}%"),
            models.Company.description.ilike(f"%{search_term}%")
        )
    )
    if user_id:
        query = query.filter(models.Company.user_id == user_id)
    return query.offset(skip).limit(limit).all()


def create_company(db: Session, company: schemas.CompanyCreate) -> models.Company:
    """Create a new company."""
    import json
    db_company = models.Company(
        user_id=company.user_id,
        domain=company.domain,
        company_name=company.company_name,
        description=company.description,
        smykm_notes=json.dumps(company.smykm_notes) if company.smykm_notes else None,
        contact_score=company.contact_score,
        search_mode=company.search_mode
    )
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company


def update_company(db: Session, company_id: int, company_update: schemas.CompanyUpdate) -> Optional[models.Company]:
    """Update company information."""
    import json
    db_company = get_company(db, company_id)
    if not db_company:
        return None

    update_data = company_update.model_dump(exclude_unset=True)

    # Handle JSON fields
    if "smykm_notes" in update_data and update_data["smykm_notes"] is not None:
        update_data["smykm_notes"] = json.dumps(update_data["smykm_notes"])

    for field, value in update_data.items():
        setattr(db_company, field, value)

    db.commit()
    db.refresh(db_company)
    return db_company


def delete_company(db: Session, company_id: int) -> bool:
    """Delete a company."""
    db_company = get_company(db, company_id)
    if not db_company:
        return False

    db.delete(db_company)
    db.commit()
    return True


# Contact CRUD operations

def create_contact(db: Session, contact: schemas.ContactCreate) -> models.Contact:
    """Create a new contact."""
    import json
    db_contact = models.Contact(
        company_id=contact.company_id,
        type=contact.type,
        value=contact.value,
        source=contact.source,
        confidence=contact.confidence,
        extra_metadata=json.dumps(contact.metadata) if contact.metadata else None,
        is_primary=contact.is_primary
    )
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact


def get_company_contacts(db: Session, company_id: int) -> List[models.Contact]:
    """Get all contacts for a company."""
    return db.query(models.Contact).filter(models.Contact.company_id == company_id).all()


def get_contacts_by_type(db: Session, company_id: int, contact_type: str) -> List[models.Contact]:
    """Get contacts by type for a company."""
    return db.query(models.Contact).filter(
        models.Contact.company_id == company_id,
        models.Contact.type == contact_type
    ).all()


# Social Media CRUD operations

def create_social_media(db: Session, social: schemas.SocialMediaCreate) -> models.SocialMedia:
    """Create a new social media profile."""
    db_social = models.SocialMedia(**social.model_dump())
    db.add(db_social)
    db.commit()
    db.refresh(db_social)
    return db_social


def get_company_social_media(db: Session, company_id: int) -> List[models.SocialMedia]:
    """Get all social media profiles for a company."""
    return db.query(models.SocialMedia).filter(models.SocialMedia.company_id == company_id).all()


# Enrichment History CRUD operations

def create_enrichment_history(db: Session, enrichment: schemas.EnrichmentHistoryCreate) -> models.EnrichmentHistory:
    """Create enrichment history entry."""
    import json
    db_enrichment = models.EnrichmentHistory(
        company_id=enrichment.company_id,
        source=enrichment.source,
        status=enrichment.status,
        details=json.dumps(enrichment.details) if enrichment.details else None
    )
    db.add(db_enrichment)
    db.commit()
    db.refresh(db_enrichment)
    return db_enrichment


def get_company_enrichment_history(db: Session, company_id: int) -> List[models.EnrichmentHistory]:
    """Get enrichment history for a company."""
    return db.query(models.EnrichmentHistory).filter(
        models.EnrichmentHistory.company_id == company_id
    ).order_by(models.EnrichmentHistory.enriched_at.desc()).all()
