"""
MongoDB Session and Connection Management

Handles MongoDB connection initialization and Beanie ODM setup.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from typing import Optional

from ..core.config import get_settings
from .mongodb_models import DOCUMENT_MODELS

settings = get_settings()

# Global client instance and initialization tracking per event loop
_mongo_client: Optional[AsyncIOMotorClient] = None
_initialized_loops = set()


async def init_db(force: bool = False):
    """
    Initialize MongoDB connection and Beanie ODM.
    Called on application startup or when entering a new event loop.

    Args:
        force: If True, reinitialize even if already initialized in this loop
    """
    global _mongo_client

    # Get current event loop ID
    try:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
    except RuntimeError:
        loop_id = None

    # Check if client needs to be recreated (e.g., if loop is closed)
    if _mongo_client:
        try:
            # Check if the client's loop is closed
            if _mongo_client.io_loop.is_closed():
                print("MongoDB client loop is closed. Reconnecting...")
                _mongo_client.close()
                _mongo_client = None
                _initialized_loops.clear()
            # Check if we are in a different loop than the client
            elif loop_id and _mongo_client.io_loop is not loop:
                print(f"MongoDB client loop mismatch ({id(_mongo_client.io_loop)} != {loop_id}). Reconnecting...")
                # We don't close the old client here as it might be used by another loop (e.g. in web server)
                # But for Celery tasks with asyncio.run, we need a new client for the current loop
                _mongo_client = None 
                # Note: In a threaded env, this global overwrite is risky. 
                # But for Celery prefork + asyncio.run, it handles the "closed loop" issue.
        except Exception as e:
            print(f"Error checking MongoDB client loop: {e}. Reconnecting...")
            _mongo_client = None

    # Create Motor async client (reuse if exists)
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(settings.DATABASE_URL)
        _initialized_loops.clear() # Reset init tracking for new client

    # Get database (MongoDB will extract db name from connection string)
    database = _mongo_client.get_default_database()

    # Initialize Beanie with all document models
    # We need to re-init Beanie if we created a new client OR if this loop hasn't initialized it yet
    if loop_id and loop_id not in _initialized_loops:
        await init_beanie(
            database=database,
            document_models=DOCUMENT_MODELS
        )
        _initialized_loops.add(loop_id)
        # print(f"MongoDB connected: {database.name} (Loop: {loop_id})")
    elif not loop_id:
         # Fallback for no-loop context (shouldn't happen with async def)
         await init_beanie(
            database=database,
            document_models=DOCUMENT_MODELS
        )


async def close_db():
    """
    Close MongoDB connection.
    Called on application shutdown.
    """
    global _mongo_client

    if _mongo_client:
        _mongo_client.close()
        print("MongoDB connection closed")


def get_mongo_client() -> AsyncIOMotorClient:
    """
    Get the MongoDB client instance.
    Use this for operations not covered by Beanie.
    """
    if _mongo_client is None:
        raise RuntimeError("MongoDB client not initialized. Call init_db() first.")
    return _mongo_client


async def get_database():
    """
    Get the default database.
    """
    client = get_mongo_client()
    return client.get_default_database()
