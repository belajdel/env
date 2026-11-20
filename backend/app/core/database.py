"""
Database Connection and Management
Async MongoDB client with Motor.
"""

from contextlib import asynccontextmanager
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global database client
_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongo() -> AsyncIOMotorDatabase:
    """Create MongoDB connection pool."""
    global _client, _db
    
    logger.info("connecting_to_mongodb", uri=settings.MONGO_URI.split("@")[-1] if "@" in settings.MONGO_URI else settings.MONGO_URI)
    
    _client = AsyncIOMotorClient(
        settings.MONGO_URI,
        maxPoolSize=settings.MONGO_MAX_POOL_SIZE,
        minPoolSize=settings.MONGO_MIN_POOL_SIZE,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
    )
    
    _db = _client[settings.MONGO_DB]
    
    # Verify connection
    await _client.admin.command("ping")
    logger.info("mongodb_connected", database=settings.MONGO_DB)
    
    return _db


async def close_mongo_connection() -> None:
    """Close MongoDB connection pool."""
    global _client, _db
    
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("mongodb_disconnected")


def get_database() -> AsyncIOMotorDatabase:
    """Get database instance (must be connected first)."""
    if _db is None:
        raise RuntimeError("Database not connected. Call connect_to_mongo() first.")
    return _db


@asynccontextmanager
async def get_db_session():
    """Context manager for database operations with automatic error handling."""
    db = get_database()
    try:
        yield db
    except Exception as e:
        logger.error("database_session_error", error=str(e))
        raise


# Collection names
class Collections:
    USERS = "users"
    ZONES = "zones"
    DEVICES = "devices"
    MEASUREMENTS = "measurements"
    MEASUREMENTS_1MIN = "measurements_1min"
    ALERT_RULES = "alert_rules"
    ALERTS = "alerts"
    AI_PREDICTIONS = "ai_predictions"
    RISK_SCORES = "risk_scores"
    REPORTS = "reports"
    AUDIT_LOGS = "audit_logs"


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all required indexes (idempotent)."""
    logger.info("creating_database_indexes")
    
    # Users
    await db[Collections.USERS].create_index(
        "username", unique=True, name="idx_username_unique"
    )
    await db[Collections.USERS].create_index(
        "email", unique=True, name="idx_email_unique"
    )
    await db[Collections.USERS].create_index("role", name="idx_role")
    await db[Collections.USERS].create_index("is_active", name="idx_is_active")
    
    # Zones
    await db[Collections.ZONES].create_index(
        "zone_id", unique=True, name="idx_zone_id_unique"
    )
    await db[Collections.ZONES].create_index("type", name="idx_type")
    
    # Devices
    await db[Collections.DEVICES].create_index(
        "device_id", unique=True, name="idx_device_id_unique"
    )
    await db[Collections.DEVICES].create_index("zone_id", name="idx_zone_id")
    await db[Collections.DEVICES].create_index("status", name="idx_status")
    
    # Alert Rules
    await db[Collections.ALERT_RULES].create_index(
        [("zone_id", ASCENDING), ("parameter", ASCENDING)],
        unique=True, name="idx_zone_param_unique"
    )
    await db[Collections.ALERT_RULES].create_index("enabled", name="idx_enabled")
    
    # Alerts
    await db[Collections.ALERTS].create_index(
        [("zone_id", ASCENDING), ("parameter", ASCENDING), ("status", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_zone_param_status_time"
    )
    await db[Collections.ALERTS].create_index(
        [("status", ASCENDING), ("level", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_status_level_time"
    )
    await db[Collections.ALERTS].create_index("acknowledged_by", name="idx_acknowledged_by")
    await db[Collections.ALERTS].create_index("resolved_by", name="idx_resolved_by")
    # TTL for resolved alerts (90 days)
    await db[Collections.ALERTS].create_index(
        "resolved_at", expireAfterSeconds=7776000, name="idx_resolved_ttl"
    )
    
    # Reports
    await db[Collections.REPORTS].create_index(
        [("zone_id", ASCENDING), ("report_type", ASCENDING), ("generated_at", DESCENDING)],
        name="idx_zone_type_time"
    )
    await db[Collections.REPORTS].create_index("generated_by", name="idx_generated_by")
    # TTL for reports (1 year)
    await db[Collections.REPORTS].create_index(
        "generated_at", expireAfterSeconds=31536000, name="idx_reports_ttl"
    )
    
    # Audit Logs (append-only, no TTL)
    await db[Collections.AUDIT_LOGS].create_index("timestamp", name="idx_timestamp")
    await db[Collections.AUDIT_LOGS].create_index(
        [("actor_id", ASCENDING), ("timestamp", DESCENDING)],
        name="idx_actor_time"
    )
    await db[Collections.AUDIT_LOGS].create_index("action", name="idx_action")
    await db[Collections.AUDIT_LOGS].create_index(
        [("resource_type", ASCENDING), ("resource_id", ASCENDING)],
        name="idx_resource"
    )
    
    logger.info("database_indexes_created")


async def seed_database(db: AsyncIOMotorDatabase) -> None:
    """Seed database with initial data if empty."""
    from datetime import datetime, timezone
    import bcrypt
    
    logger.info("seeding_database")
    
    # Check if already seeded
    user_count = await db[Collections.USERS].count_documents({})
    if user_count > 0:
        logger.info("database_already_seeded", user_count=user_count)
        return
    
    # Hash default password
    password_hash = bcrypt.hashpw(
        settings.DEFAULT_ADMIN_PASSWORD.encode(), bcrypt.gensalt(12)
    ).decode()
    
    # Seed admin user
    admin_user = {
        "username": "admin",
        "email": "admin@envmonitoring.local",
        "password_hash": password_hash,
        "full_name": "System Administrator",
        "role": "admin",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "last_login": None,
    }
    await db[Collections.USERS].insert_one(admin_user)
    
    # Seed zones
    zones = [
        {"zone_id": "prod-01", "name": "Production Line 1", "type": "production", "location": "Building A, Floor 1", "description": "Main production line", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"zone_id": "prod-02", "name": "Production Line 2", "type": "production", "location": "Building A, Floor 1", "description": "Secondary production line", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"zone_id": "prod-03", "name": "Production Line 3", "type": "production", "location": "Building A, Floor 2", "description": "Tertiary production line", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"zone_id": "store-01", "name": "Storage Area 1", "type": "storage", "location": "Building B, Floor 1", "description": "Raw material storage", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"zone_id": "store-02", "name": "Storage Area 2", "type": "storage", "location": "Building B, Floor 1", "description": "Finished goods storage", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"zone_id": "tech-01", "name": "Technical Room 1", "type": "technical", "location": "Building C, Floor 1", "description": "HVAC and electrical room", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
        {"zone_id": "tech-02", "name": "Technical Room 2", "type": "technical", "location": "Building C, Floor 2", "description": "Server and network room", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
    ]
    await db[Collections.ZONES].insert_many(zones)
    
    # Seed devices
    devices = [
        {"device_id": z["zone_id"], "zone_id": z["zone_id"], "device_type": "ESP32-WROOM-32", "firmware_version": "1.0.0", "status": "offline", "last_seen": None, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
        for z in zones
    ]
    await db[Collections.DEVICES].insert_many(devices)
    
    # Seed alert rules (49 rules: 7 zones × 7 parameters)
    alert_rules = []
    now = datetime.now(timezone.utc)
    
    # Define thresholds per zone type and parameter
    thresholds = {
        "production": {
            "temperature": {"warning_min": 18, "warning_max": 28, "critical_min": 15, "critical_max": 35, "min_duration_sec": 60, "correlation": []},
            "humidity": {"warning_min": 30, "warning_max": 70, "critical_min": 20, "critical_max": 85, "min_duration_sec": 60, "correlation": []},
            "noise": {"warning_min": None, "warning_max": 70, "critical_min": None, "critical_max": 85, "min_duration_sec": 30, "correlation": []},
            "air_quality": {"warning_min": None, "warning_max": 1000, "critical_min": None, "critical_max": 2000, "min_duration_sec": 60, "correlation": []},
            "pm25": {"warning_min": None, "warning_max": 15, "critical_min": None, "critical_max": 35, "min_duration_sec": 300, "correlation": ["pm10"]},
            "pm10": {"warning_min": None, "warning_max": 50, "critical_min": None, "critical_max": 100, "min_duration_sec": 300, "correlation": ["pm25"]},
            "voltage": {"warning_min": 200, "warning_max": 260, "critical_min": 190, "critical_max": 270, "min_duration_sec": 10, "correlation": []},
        },
        "storage": {
            "temperature": {"warning_min": 10, "warning_max": 30, "critical_min": 5, "critical_max": 35, "min_duration_sec": 60, "correlation": []},
            "humidity": {"warning_min": 30, "warning_max": 75, "critical_min": 20, "critical_max": 90, "min_duration_sec": 60, "correlation": []},
            "noise": {"warning_min": None, "warning_max": 60, "critical_min": None, "critical_max": 75, "min_duration_sec": 30, "correlation": []},
            "air_quality": {"warning_min": None, "warning_max": 800, "critical_min": None, "critical_max": 1500, "min_duration_sec": 60, "correlation": []},
            "pm25": {"warning_min": None, "warning_max": 12, "critical_min": None, "critical_max": 25, "min_duration_sec": 300, "correlation": ["pm10"]},
            "pm10": {"warning_min": None, "warning_max": 40, "critical_min": None, "critical_max": 80, "min_duration_sec": 300, "correlation": ["pm25"]},
            "voltage": {"warning_min": 200, "warning_max": 260, "critical_min": 190, "critical_max": 270, "min_duration_sec": 10, "correlation": []},
        },
        "technical": {
            "temperature": {"warning_min": 15, "warning_max": 30, "critical_min": 10, "critical_max": 40, "min_duration_sec": 60, "correlation": []},
            "humidity": {"warning_min": 20, "warning_max": 60, "critical_min": 10, "critical_max": 70, "min_duration_sec": 60, "correlation": []},
            "noise": {"warning_min": None, "warning_max": 65, "critical_min": None, "critical_max": 80, "min_duration_sec": 30, "correlation": []},
            "air_quality": {"warning_min": None, "warning_max": 600, "critical_min": None, "critical_max": 1200, "min_duration_sec": 60, "correlation": []},
            "pm25": {"warning_min": None, "warning_max": 10, "critical_min": None, "critical_max": 20, "min_duration_sec": 300, "correlation": ["pm10"]},
            "pm10": {"warning_min": None, "warning_max": 30, "critical_min": None, "critical_max": 60, "min_duration_sec": 300, "correlation": ["pm25"]},
            "voltage": {"warning_min": 210, "warning_max": 250, "critical_min": 200, "critical_max": 260, "min_duration_sec": 10, "correlation": []},
        },
    }
    
    for zone in zones:
        zone_type = zone["type"]
        zone_thresholds = thresholds[zone_type]
        for param, thresh in zone_thresholds.items():
            alert_rules.append({
                "zone_id": zone["zone_id"],
                "parameter": param,
                "warning_min": thresh["warning_min"],
                "warning_max": thresh["warning_max"],
                "critical_min": thresh["critical_min"],
                "critical_max": thresh["critical_max"],
                "min_duration_sec": thresh["min_duration_sec"],
                "correlation_rules": thresh["correlation"],
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            })
    
    await db[Collections.ALERT_RULES].insert_many(alert_rules)
    
    # Seed initial audit log
    from hashlib import sha256
    import json
    
    initial_audit = {
        "timestamp": datetime.now(timezone.utc),
        "actor_id": "system",
        "actor_role": "system",
        "action": "initialize",
        "resource_type": "database",
        "resource_id": "env_monitoring",
        "details": {"message": "Database seeded with initial data"},
        "ip_address": "127.0.0.1",
        "user_agent": "seed_database",
        "prev_hash": "0" * 64,
        "hash": "",
    }
    # Compute hash
    hash_input = initial_audit["prev_hash"] + json.dumps({
        "timestamp": initial_audit["timestamp"].isoformat(),
        "actor_id": initial_audit["actor_id"],
        "action": initial_audit["action"],
        "resource_type": initial_audit["resource_type"],
        "resource_id": initial_audit["resource_id"],
        "details": initial_audit["details"],
    }, sort_keys=True, default=str)
    initial_audit["hash"] = sha256(hash_input.encode()).hexdigest()
    
    await db[Collections.AUDIT_LOGS].insert_one(initial_audit)
    
    logger.info("database_seeded", users=1, zones=len(zones), devices=len(devices), alert_rules=len(alert_rules))


async def init_database() -> AsyncIOMotorDatabase:
    """Initialize database connection, indexes, and seed data."""
    db = await connect_to_mongo()
    await create_indexes(db)
    if settings.SEED_ON_STARTUP:
        await seed_database(db)
    return db