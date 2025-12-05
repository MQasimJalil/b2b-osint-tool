"""Database package."""
# MongoDB imports (primary)
from .mongodb_session import init_db, close_db, get_mongo_client, get_database
from . import mongodb_models

# SQLAlchemy imports (legacy - for backward compatibility if needed)
# from .base import Base
# from .session import get_db, SessionLocal, engine
# from . import models

__all__ = [
    "init_db",
    "close_db",
    "get_mongo_client",
    "get_database",
    "mongodb_models"
]
