"""
Database session management.
Provides database connection and session handling.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import os

from ..core.config import get_settings

settings = get_settings()

# Determine the database URL for SQLAlchemy
# If DATABASE_URL is MongoDB, use SQLite as fallback
if settings.DATABASE_URL.startswith(("mongodb://", "mongodb+srv://")):
    # Use SQLite as fallback for SQLAlchemy when main DB is MongoDB
    sqlalchemy_url = "sqlite:///./b2b_osint.db"
    connect_args = {"check_same_thread": False}
    pool_settings = {}
else:
    sqlalchemy_url = settings.DATABASE_URL
    connect_args = {}
    pool_settings = {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    }

# Create database engine
engine = create_engine(
    sqlalchemy_url,
    connect_args=connect_args,
    **pool_settings
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database session.
    Use this in FastAPI route dependencies.

    Yields:
        Database session

    Example:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database tables.
    Creates all tables defined in models.
    """
    from .base import Base, import_models

    # Import all models
    import_models()

    # Create all tables
    Base.metadata.create_all(bind=engine)
