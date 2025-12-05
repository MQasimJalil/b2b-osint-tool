"""
SQLAlchemy ORM models for the B2B OSINT Tool.
Based on schema_recommendation.md.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class User(Base):
    """User model for multi-tenant SaaS."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    auth0_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    companies = relationship("Company", back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    """Subscription model for user billing."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    stripe_subscription_id = Column(String, unique=True)
    plan = Column(String, nullable=False)
    status = Column(String, nullable=False)  # active, canceled, past_due
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="subscriptions")


class Job(Base):
    """Job model for background tasks."""
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String, nullable=False)  # discovery, crawling, enrichment, etc.
    status = Column(String, nullable=False)  # queued, running, completed, failed, cancelled
    progress = Column(Integer, default=0)
    config = Column(Text)  # JSON configuration
    result = Column(Text)  # JSON result
    error = Column(Text)
    celery_task_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_jobs_user_id", "user_id"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created_at", "created_at"),
    )


class Company(Base):
    """Company profile model."""
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    domain = Column(String, unique=True, nullable=False, index=True)
    company_name = Column(String)
    description = Column(Text)
    smykm_notes = Column(Text)  # JSON list of notes
    contact_score = Column(Float)
    search_mode = Column(String)

    # Vetting status
    vetting_status = Column(String)  # pending, approved, rejected
    vetting_score = Column(Float)  # Relevance score from vetting (0.0-1.0)
    vetting_details = Column(Text)  # JSON with vetting details
    vetted_at = Column(DateTime(timezone=True))

    # Crawl status
    crawl_status = Column(String)  # not_crawled, queued, crawling, completed, failed
    crawl_progress = Column(Integer, default=0)  # 0-100
    crawled_pages = Column(Integer, default=0)
    crawled_at = Column(DateTime(timezone=True))

    # Relevance status (for filtering irrelevant companies)
    relevance_status = Column(String, default='pending')  # pending, relevant, irrelevant
    relevance_reason = Column(Text)  # Reason for marking as irrelevant

    # Extraction and embedding status
    extracted_at = Column(DateTime(timezone=True))
    embedded_at = Column(DateTime(timezone=True))
    enriched_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="companies")
    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")
    social_media = relationship("SocialMedia", back_populates="company", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="company", cascade="all, delete-orphan")
    enrichment_history = relationship("EnrichmentHistory", back_populates="company", cascade="all, delete-orphan")
    email_drafts = relationship("EmailDraft", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_companies_domain", "domain"),
        Index("idx_companies_user_id", "user_id"),
    )


class Contact(Base):
    """Contact information model."""
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # email, phone, whatsapp, address, contact_page
    value = Column(String, nullable=False)
    source = Column(String)  # website, google, linkedin, social
    confidence = Column(Float)
    extra_metadata = Column(Text)  # JSON for extra details
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="contacts")

    __table_args__ = (
        Index("idx_contacts_company_id", "company_id"),
        Index("idx_contacts_value", "value"),
    )


class SocialMedia(Base):
    """Social media profiles model."""
    __tablename__ = "social_media"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String, nullable=False)  # linkedin, twitter, instagram, etc.
    url = Column(String, nullable=False)
    source = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="social_media")

    __table_args__ = (
        Index("idx_social_media_company_id", "company_id"),
    )


class Product(Base):
    """Product catalog model."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    product_external_id = Column(String)
    name = Column(String)
    brand = Column(String)
    category = Column(String)
    price = Column(String)
    url = Column(String)
    image_url = Column(String)
    description = Column(Text)
    specs = Column(Text)  # JSON blob
    reviews = Column(Text)  # JSON list
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="products")

    __table_args__ = (
        Index("idx_products_company_id", "company_id"),
    )


class EmailVerification(Base):
    """Email verification cache model."""
    __tablename__ = "email_verification"

    email = Column(String, primary_key=True)
    is_valid = Column(Boolean, nullable=False)
    reason = Column(String)
    checks_json = Column(Text)  # JSON
    mx_records = Column(Text)  # JSON list
    smtp_response = Column(Text)
    verified_at = Column(DateTime(timezone=True))
    verification_time_seconds = Column(Float)


class Blacklist(Base):
    """Email blacklist model."""
    __tablename__ = "blacklist"

    email = Column(String, primary_key=True)
    reason = Column(String)
    extra_metadata = Column(Text)  # JSON
    blacklisted_at = Column(DateTime(timezone=True), server_default=func.now())


class DiscoveryQuery(Base):
    """Discovery query cache model."""
    __tablename__ = "discovery_queries"

    id = Column(Integer, primary_key=True, index=True)
    engine = Column(String, nullable=False)
    query = Column(String, nullable=False)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    discovered_domains = relationship("DiscoveredDomain", back_populates="query")

    __table_args__ = (
        UniqueConstraint("engine", "query", name="uq_engine_query"),
    )


class DiscoveredDomain(Base):
    """Discovered domains model."""
    __tablename__ = "discovered_domains"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, nullable=False, index=True)
    query_id = Column(Integer, ForeignKey("discovery_queries.id"))
    engine = Column(String)
    discovered_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    query = relationship("DiscoveryQuery", back_populates="discovered_domains")

    __table_args__ = (
        UniqueConstraint("domain", "query_id", name="uq_domain_query"),
        Index("idx_discovered_domains_domain", "domain"),
    )


class DomainAlias(Base):
    """Domain aliases model for duplicate tracking."""
    __tablename__ = "domain_aliases"

    id = Column(Integer, primary_key=True, index=True)
    primary_domain = Column(String, nullable=False)
    alias_domain = Column(String, nullable=False)
    confidence = Column(Float)
    source = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("primary_domain", "alias_domain", name="uq_primary_alias"),
    )


class VettingHistory(Base):
    """Vetting history model."""
    __tablename__ = "vetting_history"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    source = Column(String)
    vetted_at = Column(DateTime(timezone=True), server_default=func.now())


class EnrichmentHistory(Base):
    """Enrichment history model."""
    __tablename__ = "enrichment_history"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    source = Column(String, nullable=False)
    status = Column(String, nullable=False)  # success, failure
    details = Column(Text)  # JSON blob
    enriched_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="enrichment_history")


class EmailDraft(Base):
    """Email drafts model."""
    __tablename__ = "email_drafts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    subject_lines = Column(Text)  # JSON list
    email_body = Column(Text)
    gmail_draft_id = Column(String)
    gmail_draft_created_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="email_drafts")


class CrawledPageMeta(Base):
    """Metadata for crawled pages (raw data stored in object storage)."""
    __tablename__ = "crawled_pages_meta"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, nullable=False)
    url = Column(String, nullable=False)
    content_hash = Column(String)
    depth = Column(Integer)
    crawled_at = Column(DateTime(timezone=True))
    storage_url = Column(String, nullable=False)  # URL to raw data in S3/GCS
