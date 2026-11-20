"""
Alert Engine
Threshold-based alerting with duration, correlation, and deduplication.
Pure logic - no FastAPI, MongoDB, or MQTT dependencies.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from app.core.database import get_database, Collections
from app.core.logging import get_logger
from app.models.alert import (
    AlertRuleInDB, AlertInDB, AlertPublic, AlertLevel, AlertStatus,
    VALID_PARAMETERS
)
from app.services.ai_client import get_ai_client
from app.services.websocket import get_websocket_manager

logger = get_logger(__name__)


class AlertState(str, Enum):
    """Internal alert state machine."""
    NORMAL = "normal"
    WARNING_PENDING = "warning_pending"
    WARNING_ACTIVE = "warning_active"
    CRITICAL_PENDING = "critical_pending"
    CRITICAL_ACTIVE = "critical_active"
    PREDICTIVE_ACTIVE = "predictive_active"


@dataclass
class AlertTracking:
    """Tracks alert state for a zone/parameter."""
    zone_id: str
    parameter: str
    state: AlertState = AlertState.NORMAL
    warning_start: Optional[datetime] = None
    critical_start: Optional[datetime] = None
    last_value: Optional[float] = None
    last_check: Optional[datetime] = None
    active_alert_id: Optional[str] = None  # MongoDB ObjectId as string
    acknowledged: bool = False
    correlation_triggered: bool = False


class AlertEngine:
    """
    Alert engine with threshold, duration, and correlation logic.
    Designed to be unit-testable without external dependencies.
    """
    
    def __init__(self):
        self._tracking: Dict[str, AlertTracking] = {}  # zone:param -> AlertTracking
        self._rules_cache: Dict[str, AlertRuleInDB] = {}  # zone:param -> rule
        self._last_rules_update: Optional[datetime] = None
        self._rules_cache_ttl = timedelta(minutes=5)
    
    def _get_rule_key(self, zone_id: str, parameter: str) -> str:
        return f"{zone_id}:{parameter}"
    
    async def _load_rules(self) -> None:
        """Load alert rules from database (with caching)."""
        now = datetime.now(timezone.utc)
        if (self._last_rules_update and 
            now - self._last_rules_update < self._rules_cache_ttl):
            return
        
        db = get_database()
        cursor = db[Collections.ALERT_RULES].find({"enabled": True})
        
        self._rules_cache.clear()
        async for doc in cursor:
            rule = AlertRuleInDB(**doc)
            key = self._get_rule_key(rule.zone_id, rule.parameter)
            self._rules_cache[key] = rule
        
        self._last_rules_update = now
        logger.debug("alert_rules_loaded", count=len(self._rules_cache))
    
    def _get_rule(self, zone_id: str, parameter: str) -> Optional[AlertRuleInDB]:
        """Get rule from cache."""
        return self._rules_cache.get(self._get_rule_key(zone_id, parameter))
    
    def _get_tracking(self, zone_id: str, parameter: str) -> AlertTracking:
        """Get or create tracking for zone/parameter."""
        key = self._get_rule_key(zone_id, parameter)
        if key not in self._tracking:
            self._tracking[key] = AlertTracking(zone_id=zone_id, parameter=parameter)
        return self._tracking[key]
    
    async def check_measurement(self, measurement) -> List[AlertPublic]:
        """
        Check a measurement against alert rules.
        Returns list of newly created/updated alerts.
        """
        await self._load_rules()
        
        zone_id = measurement.zone_id
        parameter = measurement.parameter
        value = measurement.value
        timestamp = measurement.timestamp
        unit = measurement.unit
        
        rule = self._get_rule(zone_id, parameter)
        if not rule:
            return []
        
        tracking = self._get_tracking(zone_id, parameter)
        tracking.last_value = value
        tracking.last_check = timestamp
        
        new_alerts = []
        
        # Check thresholds
        warning_triggered = self._check_threshold(value, rule.warning_min, rule.warning_max)
        critical_triggered = self._check_threshold(value, rule.critical_min, rule.critical_max)
        
        # State machine logic
        if critical_triggered:
            new_alerts.extend(await self._handle_critical(tracking, rule, value, timestamp, unit))
        elif warning_triggered:
            new_alerts.extend(await self._handle_warning(tracking, rule, value, timestamp, unit))
        else:
            # Value returned to normal
            new_alerts.extend(await self._handle_normal(tracking, rule, timestamp))
        
        # Check correlation rules
        if rule.correlation_rules:
            await self._check_correlation(tracking, rule, timestamp)
        
        return new_alerts
    
    def _check_threshold(self, value: float, min_thresh: Optional[float], max_thresh: Optional[float]) -> bool:
        """Check if value exceeds thresholds."""
        if min_thresh is not None and value <= min_thresh:
            return True
        if max_thresh is not None and value >= max_thresh:
            return True
        return False
    
    async def _handle_critical(
        self, tracking: AlertTracking, rule: AlertRuleInDB,
        value: float, timestamp: datetime, unit: str
    ) -> List[AlertPublic]:
        """Handle critical threshold exceedance."""
        alerts = []
        
        if tracking.state in (AlertState.CRITICAL_ACTIVE, AlertState.CRITICAL_PENDING):
            # Already in critical state
            if tracking.state == AlertState.CRITICAL_PENDING:
                # Check if duration met
                if tracking.critical_start and \
                   timestamp - tracking.critical_start >= timedelta(seconds=rule.min_duration_sec):
                    # Escalate to active
                    tracking.state = AlertState.CRITICAL_ACTIVE
                    if tracking.active_alert_id:
                        await self._update_alert_level(tracking.active_alert_id, "critical")
            return alerts
        
        # Enter critical pending
        tracking.state = AlertState.CRITICAL_PENDING
        tracking.critical_start = timestamp
        tracking.warning_start = None
        
        # Create alert immediately as critical (will be pending until duration met)
        alert = await self._create_alert(
            rule, value, rule.critical_min or rule.critical_max, 
            "critical", timestamp, unit, "pending"
        )
        tracking.active_alert_id = alert.id
        alerts.append(alert)
        
        # Schedule duration check
        asyncio.create_task(self._check_critical_duration(tracking, rule, timestamp))
        
        return alerts
    
    async def _check_critical_duration(
        self, tracking: AlertTracking, rule: AlertRuleInDB, check_time: datetime
    ) -> None:
        """Check if critical duration has been met."""
        await asyncio.sleep(rule.min_duration_sec + 1)
        
        # Re-load rules and tracking (state may have changed)
        await self._load_rules()
        rule = self._get_rule(tracking.zone_id, tracking.parameter)
        tracking = self._get_tracking(tracking.zone_id, tracking.parameter)
        
        if not rule or tracking.state != AlertState.CRITICAL_PENDING:
            return
        
        if tracking.critical_start and \
           datetime.now(timezone.utc) - tracking.critical_start >= timedelta(seconds=rule.min_duration_sec):
            tracking.state = AlertState.CRITICAL_ACTIVE
            if tracking.active_alert_id:
                await self._update_alert_level(tracking.active_alert_id, "critical")
    
    async def _handle_warning(
        self, tracking: AlertTracking, rule: AlertRuleInDB,
        value: float, timestamp: datetime, unit: str
    ) -> List[AlertPublic]:
        """Handle warning threshold exceedance."""
        alerts = []
        
        if tracking.state in (AlertState.WARNING_ACTIVE, AlertState.WARNING_PENDING):
            if tracking.state == AlertState.WARNING_PENDING:
                if tracking.warning_start and \
                   timestamp - tracking.warning_start >= timedelta(seconds=rule.min_duration_sec):
                    tracking.state = AlertState.WARNING_ACTIVE
                    if tracking.active_alert_id:
                        await self._update_alert_level(tracking.active_alert_id, "warning")
            return alerts
        
        # Don't create warning if already in critical
        if tracking.state in (AlertState.CRITICAL_PENDING, AlertState.CRITICAL_ACTIVE):
            return alerts
        
        tracking.state = AlertState.WARNING_PENDING
        tracking.warning_start = timestamp
        tracking.critical_start = None
        
        alert = await self._create_alert(
            rule, value, rule.warning_min or rule.warning_max,
            "warning", timestamp, unit, "pending"
        )
        tracking.active_alert_id = alert.id
        alerts.append(alert)
        
        asyncio.create_task(self._check_warning_duration(tracking, rule, timestamp))
        
        return alerts
    
    async def _check_warning_duration(
        self, tracking: AlertTracking, rule: AlertRuleInDB, check_time: datetime
    ) -> None:
        """Check if warning duration has been met."""
        await asyncio.sleep(rule.min_duration_sec + 1)
        
        await self._load_rules()
        rule = self._get_rule(tracking.zone_id, tracking.parameter)
        tracking = self._get_tracking(tracking.zone_id, tracking.parameter)
        
        if not rule or tracking.state != AlertState.WARNING_PENDING:
            return
        
        if tracking.warning_start and \
           datetime.now(timezone.utc) - tracking.warning_start >= timedelta(seconds=rule.min_duration_sec):
            tracking.state = AlertState.WARNING_ACTIVE
            if tracking.active_alert_id:
                await self._update_alert_level(tracking.active_alert_id, "warning")
    
    async def _handle_normal(
        self, tracking: AlertTracking, rule: AlertRuleInDB, timestamp: datetime
    ) -> List[AlertPublic]:
        """Handle value returning to normal range."""
        alerts = []
        
        if tracking.state == AlertState.NORMAL:
            return alerts
        
        # Resolve active alert if exists
        if tracking.active_alert_id:
            await self._resolve_alert(tracking.active_alert_id, "auto_resolved", timestamp)
            tracking.active_alert_id = None
        
        tracking.state = AlertState.NORMAL
        tracking.warning_start = None
        tracking.critical_start = None
        tracking.correlation_triggered = False
        
        return alerts
    
    async def _check_correlation(
        self, tracking: AlertTracking, rule: AlertRuleInDB, timestamp: datetime
    ) -> None:
        """Check cross-sensor correlation rules."""
        if tracking.correlation_triggered:
            return
        
        # For each correlated parameter, check if it also has an active alert
        db = get_database()
        for corr_param in rule.correlation_rules:
            corr_key = self._get_rule_key(tracking.zone_id, corr_param)
            corr_tracking = self._tracking.get(corr_key)
            
            if corr_tracking and corr_tracking.state in (AlertState.WARNING_ACTIVE, AlertState.CRITICAL_ACTIVE):
                # Correlation triggered - escalate if warning, or create predictive
                if tracking.state == AlertState.WARNING_ACTIVE:
                    # Escalate to critical
                    tracking.state = AlertState.CRITICAL_ACTIVE
                    if tracking.active_alert_id:
                        await self._update_alert_level(tracking.active_alert_id, "critical")
                        await self._add_correlation_note(tracking.active_alert_id, corr_param)
                elif tracking.state == AlertState.NORMAL:
                    # Create predictive alert
                    await self._create_predictive_alert(tracking, rule, corr_param, timestamp)
                
                tracking.correlation_triggered = True
                break
    
    async def _create_predictive_alert(
        self, tracking: AlertTracking, rule: AlertRuleInDB, 
        correlated_param: str, timestamp: datetime
    ) -> None:
        """Create a predictive alert based on correlation."""
        # Get correlated parameter's current value
        db = get_database()
        latest = await db[Collections.MEASUREMENTS].find_one(
            {"metadata.zone_id": tracking.zone_id, "metadata.parameter": correlated_param},
            sort=[("timestamp", -1)]
        )
        
        if not latest:
            return
        
        # Create predictive alert (lower severity, AI-informed)
        await self._create_alert(
            rule, latest["value"], 0,  # threshold not applicable for predictive
            "predictive", timestamp, latest["unit"], "open",
            metadata={
                "correlation_trigger": correlated_param,
                "correlation_value": latest["value"],
                "base_parameter": tracking.parameter,
            }
        )
    
    async def _create_alert(
        self, rule: AlertRuleInDB, value: float, threshold: float,
        level: str, timestamp: datetime, unit: str, status: str,
        metadata: Dict = None
    ) -> AlertPublic:
        """Create alert in database."""
        db = get_database()
        
        # Check for existing open alert (deduplication)
        existing = await db[Collections.ALERTS].find_one({
            "zone_id": rule.zone_id,
            "parameter": rule.parameter,
            "status": {"$in": ["open", "acknowledged"]},
        })
        
        if existing and existing["level"] == level:
            # Update existing alert
            existing["value"] = value
            existing["updated_at"] = timestamp
            await db[Collections.ALERTS].update_one(
                {"_id": existing["_id"]},
                {"$set": {"value": value, "updated_at": timestamp}}
            )
            return AlertPublic.from_db(AlertInDB(**existing))
        
        # Create new alert
        message = self._generate_alert_message(rule, value, threshold, level, unit)
        
        alert_doc = AlertInDB(
            zone_id=rule.zone_id,
            parameter=rule.parameter,
            level=level,
            value=value,
            threshold=threshold,
            unit=unit,
            message=message,
            rule_id=rule.id,
            status=status,
            metadata=metadata,
            created_at=timestamp,
            updated_at=timestamp,
        )
        
        result = await db[Collections.ALERTS].insert_one(alert_doc.model_dump(by_alias=True))
        alert_doc.id = result.inserted_id
        
        logger.warning("alert_created", 
                       zone=rule.zone_id, parameter=rule.parameter, 
                       level=level, value=value, alert_id=str(alert_doc.id))
        
        # Broadcast via WebSocket
        alert_public = AlertPublic.from_db(alert_doc)
        ws_manager = get_websocket_manager()
        asyncio.create_task(ws_manager.broadcast_alert(alert_public))
        
        return alert_public
    
    def _generate_alert_message(
        self, rule: AlertRuleInDB, value: float, threshold: float, 
        level: str, unit: str
    ) -> str:
        """Generate human-readable alert message."""
        param_name = rule.parameter.replace("_", " ").title()
        if level == "critical":
            return f"CRITICAL: {param_name} in {rule.zone_id} is {value:.1f}{unit} (threshold: {threshold:.1f}{unit})"
        elif level == "warning":
            return f"WARNING: {param_name} in {rule.zone_id} is {value:.1f}{unit} (threshold: {threshold:.1f}{unit})"
        elif level == "predictive":
            return f"PREDICTIVE: {param_name} in {rule.zone_id} may breach threshold based on correlation"
        else:
            return f"INFO: {param_name} in {rule.zone_id} is {value:.1f}{unit}"
    
    async def _update_alert_level(self, alert_id: str, new_level: str) -> None:
        """Update alert level."""
        db = get_database()
        from bson import ObjectId
        
        await db[Collections.ALERTS].update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {"level": new_level, "updated_at": datetime.now(timezone.utc)}}
        )
        
        # Broadcast update for critical escalation
        ws_manager = get_websocket_manager()
        asyncio.create_task(ws_manager.broadcast_alert_update(alert_id, new_level, "system"))
    
    async def _add_correlation_note(self, alert_id: str, correlated_param: str) -> None:
        """Add correlation note to alert metadata."""
        db = get_database()
        from bson import ObjectId
        
        await db[Collections.ALERTS].update_one(
            {"_id": ObjectId(alert_id)},
            {"$set": {
                "metadata.correlation_trigger": correlated_param,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
    
    async def _resolve_alert(self, alert_id: str, resolved_by: str, timestamp: datetime) -> None:
        """Resolve an alert."""
        db = get_database()
        from bson import ObjectId
        
        result = await db[Collections.ALERTS].update_one(
            {"_id": ObjectId(alert_id), "status": {"$in": ["open", "acknowledged"]}},
            {"$set": {
                "status": "resolved",
                "resolved_by": resolved_by,
                "resolved_at": timestamp,
                "updated_at": timestamp,
            }}
        )
        
        if result.modified_count:
            logger.info("alert_resolved", alert_id=alert_id, resolved_by=resolved_by)
            # Broadcast update
            ws_manager = get_websocket_manager()
            asyncio.create_task(ws_manager.broadcast_alert_update(alert_id, "resolved", resolved_by))
    
    # Public API methods for alert management
    
    async def acknowledge_alert(self, alert_id: str, user_id: str) -> Optional[AlertPublic]:
        """Acknowledge an alert."""
        db = get_database()
        from bson import ObjectId
        
        result = await db[Collections.ALERTS].find_one_and_update(
            {"_id": ObjectId(alert_id), "status": "open"},
            {"$set": {
                "status": "acknowledged",
                "acknowledged_by": user_id,
                "acknowledged_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
            return_document=True,
        )
        
        if result:
            logger.info("alert_acknowledged", alert_id=alert_id, user_id=user_id)
            alert_public = AlertPublic.from_db(AlertInDB(**result))
            # Broadcast update
            ws_manager = get_websocket_manager()
            asyncio.create_task(ws_manager.broadcast_alert_update(alert_id, "acknowledged", user_id))
            return alert_public
        return None
    
    async def resolve_alert(self, alert_id: str, user_id: str, notes: str = None) -> Optional[AlertPublic]:
        """Manually resolve an alert."""
        db = get_database()
        from bson import ObjectId
        
        result = await db[Collections.ALERTS].find_one_and_update(
            {"_id": ObjectId(alert_id), "status": {"$in": ["open", "acknowledged"]}},
            {"$set": {
                "status": "resolved",
                "resolved_by": user_id,
                "resolved_at": datetime.now(timezone.utc),
                "resolution_notes": notes,
                "updated_at": datetime.now(timezone.utc),
            }},
            return_document=True,
        )
        
        if result:
            logger.info("alert_resolved_manual", alert_id=alert_id, user_id=user_id)
            alert_public = AlertPublic.from_db(AlertInDB(**result))
            # Broadcast update
            ws_manager = get_websocket_manager()
            asyncio.create_task(ws_manager.broadcast_alert_update(alert_id, "resolved", user_id))
            return alert_public
        return None
    
    async def get_active_alerts(self, zone_id: str = None) -> List[AlertPublic]:
        """Get all active (open/acknowledged) alerts."""
        db = get_database()
        
        query = {"status": {"$in": ["open", "acknowledged"]}}
        if zone_id:
            query["zone_id"] = zone_id
        
        cursor = db[Collections.ALERTS].find(query).sort("created_at", -1)
        alerts = []
        async for doc in cursor:
            alerts.append(AlertPublic.from_db(AlertInDB(**doc)))
        return alerts
    
    async def get_alert_summary(self) -> Dict:
        """Get alert summary for dashboard."""
        db = get_database()
        
        # Count by status
        pipeline = [
            {"$match": {"status": {"$in": ["open", "acknowledged", "resolved"]}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        by_status = {}
        async for doc in db[Collections.ALERTS].aggregate(pipeline):
            by_status[doc["_id"]] = doc["count"]
        
        # Count by level (active only)
        pipeline = [
            {"$match": {"status": {"$in": ["open", "acknowledged"]}}},
            {"$group": {"_id": "$level", "count": {"$sum": 1}}},
        ]
        by_level = {}
        async for doc in db[Collections.ALERTS].aggregate(pipeline):
            by_level[doc["_id"]] = doc["count"]
        
        # Count by zone (active only)
        pipeline = [
            {"$match": {"status": {"$in": ["open", "acknowledged"]}}},
            {"$group": {"_id": "$zone_id", "count": {"$sum": 1}}},
        ]
        by_zone = {}
        async for doc in db[Collections.ALERTS].aggregate(pipeline):
            by_zone[doc["_id"]] = doc["count"]
        
        # Recent critical alerts
        recent_critical = []
        cursor = db[Collections.ALERTS].find({
            "level": "critical",
            "status": {"$in": ["open", "acknowledged"]},
        }).sort("created_at", -1).limit(5)
        async for doc in cursor:
            recent_critical.append(AlertPublic.from_db(AlertInDB(**doc)))
        
        return {
            "total_open": by_status.get("open", 0),
            "total_acknowledged": by_status.get("acknowledged", 0),
            "total_resolved_today": by_status.get("resolved", 0),  # Simplified
            "by_level": by_level,
            "by_zone": by_zone,
            "recent_critical": recent_critical,
        }


_alert_engine: Optional[AlertEngine] = None


def get_alert_engine() -> AlertEngine:
    """Get singleton AlertEngine instance."""
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine