"""
MongoDB Models using Beanie ODM

All models for the B2B OSINT Tool using MongoDB as the primary database.
Beanie provides async ODM with Pydantic validation.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import EmailStr, Field
from beanie import Document, Indexed, Link
from pymongo import IndexModel, ASCENDING, DESCENDING


# ============================================
# User & Authentication Models
# ============================================

class User(Document):
    """User account model"""
    auth0_id: Indexed(str, unique=True)
    email: Indexed(EmailStr, unique=True)
    name: Optional[str] = None
    picture: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("auth0_id", ASCENDING)], unique=True),
            IndexModel([("email", ASCENDING)], unique=True),
        ]


class Subscription(Document):
    """User subscription model"""
    user_id: Indexed(str)  # Reference to User._id
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    plan_type: str = "free"  # free, starter, professional, enterprise
    status: str = "active"  # active, cancelled, past_due
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "subscriptions"
        indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("stripe_customer_id", ASCENDING)]),
        ]


# ============================================
# Company & Contact Models
# ============================================

class Contact(Document):
    """Contact information (embedded or standalone)"""
    type: str  # email, phone, whatsapp, linkedin_individual, etc.
    value: str
    confidence: float = 1.0
    source: str = "website"  # website, google, linkedin, etc.
    verified: bool = False
    is_primary: bool = False
    found_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = {}


class SocialMedia(Document):
    """Social media links (embedded)"""
    platform: str  # linkedin, instagram, facebook, twitter, etc.
    url: str
    source: str = "website"
    verified: bool = False


class Company(Document):
    """Company profile model"""
    user_id: Indexed(str)  # Reference to User._id
    domain: Indexed(str, unique=True)
    company_name: Optional[str] = None
    description: Optional[str] = None
    smykm_notes: List[str] = []  # Show Me You Know Me notes

    # Contacts (embedded documents)
    contacts: List[Dict[str, Any]] = []  # List of contact dicts
    social_media: List[Dict[str, Any]] = []  # List of social media dicts

    # Enrichment metadata
    contact_score: Optional[str] = None  # high, medium, low
    search_mode: Optional[str] = None  # lenient, aggressive
    enrichment_status: Optional[Dict[str, Any]] = None

    # Email verification results
    email_verification: Dict[str, Any] = {}

    # Relevance filtering (for companies with no relevant products)
    relevance_status: str = "pending"  # pending, relevant, irrelevant
    relevance_reason: Optional[str] = None  # Reason for marking as irrelevant

    # Crawl fields
    crawl_status: str = "not_crawled"  # not_crawled, queued, crawling, completed, failed
    crawl_progress: int = 0  # 0-100
    crawled_pages: int = 0  # Number of pages crawled
    crawled_at: Optional[datetime] = None

    # Timestamps
    extracted_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None
    embedded_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "companies"
        indexes = [
            IndexModel([("domain", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("domain", ASCENDING), ("user_id", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("relevance_status", ASCENDING)]),  # For filtering irrelevant companies
        ]


class Product(Document):
    """Product catalog model"""
    company_id: Indexed(str)  # Reference to Company._id
    domain: Indexed(str)  # Denormalized for quick filtering

    product_external_id: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    specs: Dict[str, Any] = {}
    reviews: List[str] = []

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "products"
        indexes = [
            IndexModel([("company_id", ASCENDING)]),
            IndexModel([("domain", ASCENDING)]),
            IndexModel([("brand", ASCENDING)]),
            IndexModel([("category", ASCENDING)]),
        ]


# ============================================
# Discovery & Vetting Models
# ============================================

class DiscoveredDomain(Document):
    """Discovered domain from search engines"""
    domain: Indexed(str)
    engine: str  # google, bing, brave
    query: str
    user_id: Optional[str] = None  # User who discovered it

    # Soft vetting results
    has_cart: bool = False
    has_product_schema: bool = False
    has_platform_fp: bool = False

    discovered_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "discovered_domains"
        indexes = [
            IndexModel([("domain", ASCENDING)]),
            IndexModel([("engine", ASCENDING)]),
            IndexModel([("discovered_at", DESCENDING)]),
        ]


class QueryCache(Document):
    """Cache for completed search queries"""
    engine: str
    query: str
    domains: List[str] = []
    completed_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "query_cache"
        indexes = [
            IndexModel([("engine", ASCENDING), ("query", ASCENDING)], unique=True),
        ]


class VettingResult(Document):
    """Soft vetting cache for domains"""
    domain: Indexed(str, unique=True)
    has_product_schema: bool = False
    has_cart: bool = False
    has_platform_fp: bool = False
    decision: str = "UNKNOWN"  # YES, NO, UNKNOWN
    vetted_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "vetting_results"
        indexes = [
            IndexModel([("domain", ASCENDING)], unique=True),
        ]


# ============================================
# Crawling Models
# ============================================

class CrawledPage(Document):
    """Individual crawled page"""
    domain: Indexed(str)
    url: Indexed(str)
    title: Optional[str] = None
    content: str = ""
    content_hash: Indexed(str)  # SHA256 for deduplication
    depth: int = 0
    crawled_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crawled_pages"
        indexes = [
            IndexModel([("domain", ASCENDING)]),
            IndexModel([("url", ASCENDING)]),
            IndexModel([("content_hash", ASCENDING)]),
            IndexModel([("crawled_at", DESCENDING)]),
        ]


class CrawlState(Document):
    """Crawl state tracking for a domain"""
    domain: Indexed(str, unique=True)
    visited_urls: List[str] = []
    visited_hashes: List[str] = []
    is_complete: bool = False
    pages_crawled: int = 0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Settings:
        name = "crawl_states"
        indexes = [
            IndexModel([("domain", ASCENDING)], unique=True),
        ]


# ============================================
# Enrichment Models
# ============================================

class EnrichmentResult(Document):
    """Contact enrichment results"""
    domain: Indexed(str, unique=True)
    company_id: Optional[str] = None  # Reference to Company._id

    phones: List[Dict[str, Any]] = []
    whatsapp: List[Dict[str, Any]] = []
    linkedin_profiles: List[Dict[str, Any]] = []
    social_media: Dict[str, Dict[str, Any]] = {}

    sources_checked: List[str] = []
    search_mode: str = "lenient"  # lenient, aggressive
    contact_score: str = "low"  # high, medium, low
    notes: str = ""

    enriched_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "enrichment_results"
        indexes = [
            IndexModel([("domain", ASCENDING)], unique=True),
            IndexModel([("company_id", ASCENDING)]),
        ]


# ============================================
# Email & Campaign Models
# ============================================

class Campaign(Document):
    """Outreach campaign model"""
    user_id: Indexed(str)  # Reference to User._id
    name: str
    status: str = "draft"  # draft, active, completed, archived
    type: str = "email_outreach"
    
    # Stats
    stats: Dict[str, int] = {
        "total_companies": 0,
        "emails_generated": 0,
        "emails_sent": 0,
        "emails_opened": 0,
        "emails_clicked": 0
    }

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "campaigns"
        indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]


class EmailDraft(Document):
    """Generated email drafts"""
    company_id: Indexed(str)  # Reference to Company._id
    domain: Indexed(str)
    user_id: Indexed(str)  # User who generated it
    campaign_id: Optional[Indexed(str)] = None # Reference to Campaign._id

    # Content
    subject: Optional[str] = None # Selected subject line
    subject_line_options: List[str] = [] # AI generated options
    body: Optional[str] = None
    to_emails: List[str] = []

    # Lifecycle
    status: str = "draft" # draft, generating, ready, sent, failed
    last_error: Optional[str] = None

    # Metadata
    generation_method: str = "gemini"  # gemini, openai, anthropic
    playbook_used: Optional[str] = None

    sent: bool = False
    sent_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "email_drafts"
        indexes = [
            IndexModel([("company_id", ASCENDING)]),
            IndexModel([("domain", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("campaign_id", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]


class EmailVerificationCache(Document):
    """Email verification results cache"""
    email: Indexed(str, unique=True)
    is_valid: bool = False
    mx_valid: bool = False
    smtp_valid: bool = False
    error: Optional[str] = None
    verified_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "email_verification_cache"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
        ]


class EmailWhitelist(Document):
    """Whitelisted email domains"""
    domain: Indexed(str, unique=True)
    reason: str = "manual"
    added_by: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "email_whitelist"
        indexes = [
            IndexModel([("domain", ASCENDING)], unique=True),
        ]


# ============================================
# RAG Models
# ============================================

class RAGEmbedding(Document):
    """RAG embeddings stored in MongoDB"""
    domain: Indexed(str)
    chunk_id: Indexed(str, unique=True)
    collection_name: str  # raw_pages, products, companies

    # Content
    content: str  # The actual text chunk
    embedding: List[float]  # 1536 dimensions for OpenAI text-embedding-3-small

    # Content metadata
    content_hash: str
    tokens: int

    # Source metadata
    url: Optional[str] = None
    title: Optional[str] = None

    # Collection-specific metadata
    metadata: Dict[str, Any] = {}

    embedded_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "rag_embeddings"
        indexes = [
            IndexModel([("domain", ASCENDING)]),
            IndexModel([("chunk_id", ASCENDING)], unique=True),
            IndexModel([("collection_name", ASCENDING)]),
            IndexModel([("content_hash", ASCENDING)]),
        ]


class RAGQuery(Document):
    """RAG query history for analytics"""
    user_id: Indexed(str)
    query: str
    collections_searched: List[str] = []
    filters: Dict[str, Any] = {}
    results_count: int = 0

    queried_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "rag_queries"
        indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("queried_at", DESCENDING)]),
        ]


# ============================================
# Document List for Beanie Initialization
# ============================================

DOCUMENT_MODELS = [
    User,
    Subscription,
    Company,
    Product,
    DiscoveredDomain,
    QueryCache,
    VettingResult,
    CrawledPage,
    CrawlState,
    EnrichmentResult,
    Campaign,
    EmailDraft,
    EmailVerificationCache,
    EmailWhitelist,
    RAGEmbedding,
    RAGQuery,
]
