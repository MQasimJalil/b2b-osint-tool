"""
Database base configuration.
Defines the declarative base for SQLAlchemy models.
"""
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Import all models here to ensure they're registered with Base
# This is important for Alembic migrations
def import_models():
    """Import all models to register them with Base."""
    from . import models  # noqa: F401
