"""
Core configuration module for the B2B OSINT Tool.
Manages all environment variables and application settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional, List, Union
import os
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses pydantic-settings for validation and type checking.
    """

    # Application
    APP_NAME: str = "B2B OSINT Tool"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development, staging, production

    # API
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/b2b_osint"
    # Alternative: Use SQLite for development
    # DATABASE_URL: str = "sqlite:///./b2b_osint.db"

    # Authentication
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Auth0 Configuration (for production)
    AUTH0_DOMAIN: Optional[str] = None
    AUTH0_API_AUDIENCE: Optional[str] = None
    AUTH0_ISSUER: Optional[str] = None
    AUTH0_ALGORITHMS: str = "RS256"

    # Stripe Configuration
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Redis (for Celery)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # API Keys
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None
    GOOGLE_SEARCH_KEY: Optional[str] = None  # Alternative for Google Custom Search
    GOOGLE_SEARCH_ENGINE_ID: Optional[str] = None  # Alternative for Google CSE ID
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Gmail Configuration
    GMAIL_CREDENTIALS_FILE: str = "credentials.json"
    GMAIL_TOKEN_FILE: str = "token.json"

    # External Scraping Services
    BRIGHT_DATA_API_KEY: Optional[str] = None
    SCRAPER_API_KEY: Optional[str] = None
    BROWSERLESS_API_KEY: Optional[str] = None

    # Search Configuration
    BING_API_KEY: Optional[str] = None
    SERPAPI_KEY: Optional[str] = None

    # Cloud Storage (for crawled data)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    # Elasticsearch/OpenSearch (for full-text search)
    ELASTICSEARCH_URL: Optional[str] = None
    ELASTICSEARCH_API_KEY: Optional[str] = None

    # Application Limits
    MAX_CRAWL_DEPTH: int = 3
    MAX_PAGES_PER_DOMAIN: int = 100
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # OpenAI Rate Limiting
    OPENAI_CONCURRENT_REQUESTS: int = 2
    OPENAI_REQUEST_DELAY: float = 1.5

    # Email Verification
    EMAIL_VERIFICATION_TIMEOUT: int = 10

    # Logging
    LOG_LEVEL: str = "INFO"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = '["http://localhost:3000", "http://localhost:8000"]'

    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from string or list"""
        if isinstance(v, str):
            if not v or v.strip() == '':
                return ["http://localhost:3000", "http://localhost:8000"]
            try:
                import json
                return json.loads(v)
            except:
                # If it's a comma-separated string
                return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
        case_sensitive=True,
        extra='ignore'
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Use this function to access settings throughout the application.
    """
    return Settings()


# Convenience instance for imports
settings = get_settings()
