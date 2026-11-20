"""
AI Service Database Module
Async MongoDB connection with Motor
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from pymongo import ASCENDING, DESCENDING, TEXT
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Collections
class Collections:
    MEASUREMENTS = "measurements"
    MEASUREMENTS_1MIN = "measurements_1min"
    ALERTS = "alerts"
    ALERT_RULES = "alert_rules"
    AI_PREDICTIONS = "ai_predictions"
    AI_MODELS = "ai_models"
    RISK_SCORES = "risk_scores"
    TRAINING_DATA = "training_data"
    MODEL_METADATA = "model_metadata"


# Global client
_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None


async def init_database() -> AsyncIOMotorDatabase:
    """Initialize database connection and create indexes."""
    global _client, _database
    
    if _database is not None:
        return _database
    
    logger.info("initializing_database", uri=settings.MONGO_URI, db=settings.MONGO_DB)
    
    _client = AsyncIOMotorClient(
        settings.MONGO_URI,
        maxPoolSize=20,
        minPoolSize=5,
        serverSelectionTimeoutMS=10000,
    )
    
    _database = _client[settings.MONGO_DB]
    
    # Test connection
    try:
        await _client.admin.command("ping")
        logger.info("database_connected")
    except PyMongoError as e:
        logger.error("database_connection_failed", error=str(e))
        raise
    
    # Create indexes
    await create_indexes()
    
    return _database


async def create_indexes() -> None:
    """Create database indexes for AI collections."""
    db = _database
    
    # AI Predictions
    await db[Collections.AI_PREDICTIONS].create_indexes([
        [("zone_id", ASCENDING), ("timestamp", DESCENDING)],
        [("model_type", ASCENDING), ("timestamp", DESCENDING)],
        [("prediction_type", ASCENDING)],
        [("created_at", DESCENDING)],
    ])
    
    # AI Models
    await db[Collections.AI_MODELS].create_indexes([
        [("model_type", ASCENDING), ("version", DESCENDING)],
        [("is_active", ASCENDING)],
        [("created_at", DESCENDING)],
    ])
    
    # Risk Scores
    await db[Collections.RISK_SCORES].create_indexes([
        [("zone_id", ASCENDING), ("timestamp", DESCENDING)],
        [("level", ASCENDING)],
    ])
    
    # Training Data
    await db[Collections.TRAINING_DATA].create_indexes([
        [("zone_id", ASCENDING), ("parameter", ASCENDING), ("timestamp", ASCENDING)],
        [("label", ASCENDING)],
        [("is_synthetic", ASCENDING)],
    ])
    
    # Model Metadata
    await db[Collections.MODEL_METADATA].create_indexes([
        [("model_type", ASCENDING), ("version", DESCENDING)],
        [("created_at", DESCENDING)],
    ])
    
    logger.info("database_indexes_created")


def get_database() -> AsyncIOMotorDatabase:
    """Get database instance."""
    if _database is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _database


async def close_mongo_connection() -> None:
    """Close MongoDB connection."""
    global _client, _database
    if _client:
        _client.close()
        _client = None
        _database = None
        logger.info("database_connection_closed")