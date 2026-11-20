"""
Audit Log Service
Append-only logging with hash chain for tamper evidence.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from pymongo import ASCENDING, DESCENDING

from app.core.database import get_database, Collections
from app.core.logging import get_logger
from app.models.audit import AuditLogCreate, AuditLogInDB, AuditLogPublic, AuditLogQuery

logger = get_logger(__name__)


class AuditService:
    """Audit logging service with hash chain."""
    
    def __init__(self):
        self._last_hash_cache: Optional[str] = None
    
    async def _get_last_hash(self) -> str:
        """Get the hash of the last audit log entry."""
        if self._last_hash_cache:
            return self._last_hash_cache
        
        db = get_database()
        last_entry = await db[Collections.AUDIT_LOGS].find_one(
            sort=[("timestamp", DESCENDING)]
        )
        
        if last_entry:
            self._last_hash_cache = last_entry["hash"]
            return self._last_hash_cache
        
        # Genesis hash
        return "0" * 64
    
    def _compute_hash(self, prev_hash: str, entry: AuditLogCreate) -> str:
        """Compute SHA256 hash for audit entry."""
        # Create deterministic JSON for hashing
        hash_data = {
            "prev_hash": prev_hash,
            "timestamp": entry.timestamp.isoformat() if hasattr(entry.timestamp, 'isoformat') else str(entry.timestamp),
            "actor_id": entry.actor_id,
            "actor_role": entry.actor_role,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "details": entry.details or {},
            "ip_address": entry.ip_address or "",
            "user_agent": entry.user_agent or "",
        }
        
        # Canonical JSON (sorted keys)
        json_str = json.dumps(hash_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    async def log(
        self,
        actor_id: str,
        actor_role: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLogInDB:
        """Create an audit log entry."""
        db = get_database()
        
        # Get previous hash
        prev_hash = await self._get_last_hash()
        
        # Create entry
        entry = AuditLogCreate(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        # Compute hash
        entry_hash = self._compute_hash(prev_hash, entry)
        
        # Create DB document
        now = datetime.now(timezone.utc)
        audit_doc = AuditLogInDB(
            **entry.model_dump(),
            timestamp=now,
            prev_hash=prev_hash,
            hash=entry_hash,
        )
        
        # Insert
        result = await db[Collections.AUDIT_LOGS].insert_one(audit_doc.model_dump(by_alias=True))
        audit_doc.id = result.inserted_id
        
        # Update cache
        self._last_hash_cache = entry_hash
        
        logger.debug("audit_log_created", 
                     actor_id=actor_id, action=action, 
                     resource_type=resource_type, resource_id=resource_id)
        
        return audit_doc
    
    async def query(self, query: AuditLogQuery) -> List[AuditLogPublic]:
        """Query audit logs with filters."""
        db = get_database()
        
        filter_dict = {}
        if query.actor_id:
            filter_dict["actor_id"] = query.actor_id
        if query.actor_role:
            filter_dict["actor_role"] = query.actor_role
        if query.action:
            filter_dict["action"] = query.action
        if query.resource_type:
            filter_dict["resource_type"] = query.resource_type
        if query.resource_id:
            filter_dict["resource_id"] = query.resource_id
        if query.start or query.end:
            filter_dict["timestamp"] = {}
            if query.start:
                filter_dict["timestamp"]["$gte"] = query.start
            if query.end:
                filter_dict["timestamp"]["$lte"] = query.end
        
        cursor = db[Collections.AUDIT_LOGS].find(filter_dict).sort("timestamp", DESCENDING).skip(query.offset).limit(query.limit)
        
        results = []
        async for doc in cursor:
            audit = AuditLogInDB(**doc)
            results.append(AuditLogPublic.from_db(audit))
        
        return results
    
    async def verify_chain(self, start: datetime = None, end: datetime = None) -> Dict[str, Any]:
        """Verify the hash chain integrity."""
        db = get_database()
        
        filter_dict = {}
        if start or end:
            filter_dict["timestamp"] = {}
            if start:
                filter_dict["timestamp"]["$gte"] = start
            if end:
                filter_dict["timestamp"]["$lte"] = end
        
        cursor = db[Collections.AUDIT_LOGS].find(filter_dict).sort("timestamp", ASCENDING)
        
        prev_hash = "0" * 64
        verified = 0
        broken = 0
        broken_entries = []
        
        async for doc in cursor:
            # Recompute hash
            entry_data = {
                "prev_hash": prev_hash,
                "timestamp": doc["timestamp"].isoformat() if hasattr(doc["timestamp"], 'isoformat') else str(doc["timestamp"]),
                "actor_id": doc["actor_id"],
                "actor_role": doc["actor_role"],
                "action": doc["action"],
                "resource_type": doc["resource_type"],
                "resource_id": doc["resource_id"],
                "details": doc.get("details") or {},
                "ip_address": doc.get("ip_address") or "",
                "user_agent": doc.get("user_agent") or "",
            }
            
            json_str = json.dumps(entry_data, sort_keys=True, separators=(",", ":"))
            computed_hash = hashlib.sha256(json_str.encode()).hexdigest()
            
            if computed_hash == doc["hash"] and doc["prev_hash"] == prev_hash:
                verified += 1
            else:
                broken += 1
                broken_entries.append({
                    "id": str(doc["_id"]),
                    "timestamp": doc["timestamp"],
                    "expected_hash": computed_hash,
                    "actual_hash": doc["hash"],
                    "expected_prev_hash": prev_hash,
                    "actual_prev_hash": doc["prev_hash"],
                })
            
            prev_hash = doc["hash"]
        
        return {
            "verified": verified,
            "broken": broken,
            "intact": broken == 0,
            "broken_entries": broken_entries,
            "last_hash": prev_hash,
        }
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get audit log statistics."""
        db = get_database()
        
        total = await db[Collections.AUDIT_LOGS].count_documents({})
        
        # Count by action
        pipeline = [
            {"$group": {"_id": "$action", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
        by_action = {}
        async for doc in db[Collections.AUDIT_LOGS].aggregate(pipeline):
            by_action[doc["_id"]] = doc["count"]
        
        # Count by actor
        pipeline = [
            {"$group": {"_id": "$actor_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
        by_actor = {}
        async for doc in db[Collections.AUDIT_LOGS].aggregate(pipeline):
            by_actor[doc["_id"]] = doc["count"]
        
        # Latest entry
        latest = await db[Collections.AUDIT_LOGS].find_one(sort=[("timestamp", DESCENDING)])
        
        return {
            "total_entries": total,
            "by_action": by_action,
            "by_actor": by_actor,
            "latest_entry": latest["timestamp"] if latest else None,
            "chain_verified": False,  # Would need full verification
        }


_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get singleton AuditService instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service