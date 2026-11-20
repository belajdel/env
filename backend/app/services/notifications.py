"""
Notification Service
Push notifications via Firebase Cloud Messaging (FCM) with Telegram fallback.
"""

import asyncio
import httpx
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum

from app.core.config import settings
from app.core.database import get_database, Collections
from app.core.logging import get_logger
from app.models.alert import AlertPublic, AlertLevel

logger = get_logger(__name__)


class NotificationChannel(str, Enum):
    """Notification delivery channels."""
    FCM = "fcm"
    TELEGRAM = "telegram"
    WEBSOCKET = "websocket"


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationService:
    """Multi-channel notification service."""
    
    def __init__(self):
        self.fcm_enabled = bool(settings.FCM_SERVER_KEY)
        self.telegram_enabled = bool(settings.TELEGRAM_BOT_TOKEN)
        
        self.fcm_server_key = settings.FCM_SERVER_KEY
        self.fcm_project_id = settings.FCM_PROJECT_ID
        self.fcm_url = "https://fcm.googleapis.com/fcm/send"
        
        self.telegram_bot_token = settings.TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = settings.TELEGRAM_CHAT_ID
        self.telegram_url = f"https://api.telegram.org/bot{self.telegram_bot_token}"
        
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(max_connections=20),
            )
        return self._http_client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
    
    # ============================================
    # FCM Notifications
    # ============================================
    
    async def send_fcm(
        self, 
        tokens: List[str], 
        title: str, 
        body: str, 
        data: Dict[str, Any] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
    ) -> Dict[str, Any]:
        """Send FCM push notification."""
        if not self.fcm_enabled or not tokens:
            return {"success": False, "error": "FCM not configured or no tokens"}
        
        client = await self._get_client()
        
        headers = {
            "Authorization": f"key={self.fcm_server_key}",
            "Content-Type": "application/json",
        }
        
        # Android/iOS config
        android_config = {
            "priority": priority.value,
            "notification": {
                "channel_id": "alerts",
                "priority": priority.value,
                "default_sound": True,
                "default_vibrate_timings": True,
            },
        }
        
        apns_config = {
            "payload": {
                "aps": {
                    "sound": "default",
                    "badge": 1,
                    "content-available": 1,
                }
            }
        }
        
        payload = {
            "registration_ids": tokens,
            "notification": {
                "title": title,
                "body": body,
            },
            "data": data or {},
            "android": android_config,
            "apns": apns_config,
            "priority": priority.value,
        }
        
        try:
            response = await client.post(self.fcm_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            success_count = result.get("success", 0)
            failure_count = result.get("failure", 0)
            
            logger.info("fcm_sent", success=success_count, failure=failure_count)
            
            # Handle token canonical IDs (updated tokens)
            if "results" in result:
                for i, res in enumerate(result["results"]):
                    if "registration_id" in res:
                        # Token updated - should update in database
                        old_token = tokens[i]
                        new_token = res["registration_id"]
                        await self._update_fcm_token(old_token, new_token)
            
            return {"success": True, "success_count": success_count, "failure_count": failure_count, "results": result.get("results", [])}
            
        except Exception as e:
            logger.error("fcm_send_failed", error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _update_fcm_token(self, old_token: str, new_token: str) -> None:
        """Update FCM token in user preferences."""
        db = get_database()
        await db[Collections.USERS].update_many(
            {"notification_preferences.fcm_tokens": old_token},
            {"$set": {"notification_preferences.fcm_tokens.$": new_token}}
        )
    
    # ============================================
    # Telegram Notifications
    # ============================================
    
    async def send_telegram(
        self, 
        message: str, 
        chat_id: str = None,
        parse_mode: str = "HTML",
    ) -> Dict[str, Any]:
        """Send Telegram message."""
        if not self.telegram_enabled:
            return {"success": False, "error": "Telegram not configured"}
        
        client = await self._get_client()
        
        target_chat_id = chat_id or self.telegram_chat_id
        if not target_chat_id:
            return {"success": False, "error": "No chat ID configured"}
        
        payload = {
            "chat_id": target_chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        
        try:
            response = await client.post(f"{self.telegram_url}/sendMessage", json=payload)
            response.raise_for_status()
            result = response.json()
            
            logger.info("telegram_sent", chat_id=target_chat_id)
            return {"success": True, "message_id": result.get("result", {}).get("message_id")}
            
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e))
            return {"success": False, "error": str(e)}
    
    async def send_telegram_alert(self, alert: AlertPublic) -> Dict[str, Any]:
        """Send formatted alert via Telegram."""
        level_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🔴",
            "predictive": "🔮",
        }
        
        emoji = level_emoji.get(alert.level, "📢")
        
        message = (
            f"{emoji} <b>{alert.level.upper()} ALERT</b>\n\n"
            f"<b>Zone:</b> {alert.zone_id}\n"
            f"<b>Parameter:</b> {alert.parameter.replace('_', ' ').title()}\n"
            f"<b>Value:</b> {alert.value:.1f} {alert.unit}\n"
            f"<b>Threshold:</b> {alert.threshold:.1f} {alert.unit}\n"
            f"<b>Status:</b> {alert.status.upper()}\n"
            f"<b>Time:</b> {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"{alert.message}"
        )
        
        return await self.send_telegram(message)
    
    # ============================================
    # High-Level Alert Notifications
    # ============================================
    
    async def notify_alert(self, alert: AlertPublic, user_tokens: Dict[str, List[str]] = None) -> Dict[str, Any]:
        """
        Send alert notification through all available channels.
        
        Args:
            alert: The alert to notify about
            user_tokens: Dict of user_id -> list of FCM tokens (for targeted notifications)
        """
        results = {}
        
        # Determine priority based on alert level
        priority_map = {
            "info": NotificationPriority.LOW,
            "warning": NotificationPriority.NORMAL,
            "critical": NotificationPriority.CRITICAL,
            "predictive": NotificationPriority.HIGH,
        }
        priority = priority_map.get(alert.level, NotificationPriority.NORMAL)
        
        # FCM: Send to all users with tokens (or specific users)
        if self.fcm_enabled:
            all_tokens = []
            if user_tokens:
                for tokens in user_tokens.values():
                    all_tokens.extend(tokens)
            else:
                # Get all active FCM tokens from database
                all_tokens = await self._get_all_fcm_tokens()
            
            if all_tokens:
                # Deduplicate
                unique_tokens = list(set(all_tokens))
                fcm_result = await self.send_fcm(
                    tokens=unique_tokens,
                    title=f"{alert.level.upper()}: {alert.parameter.replace('_', ' ').title()}",
                    body=f"Zone {alert.zone_id}: {alert.value:.1f} {alert.unit} (threshold: {alert.threshold:.1f} {alert.unit})",
                    data={
                        "alert_id": alert.id,
                        "zone_id": alert.zone_id,
                        "parameter": alert.parameter,
                        "level": alert.level,
                        "value": str(alert.value),
                        "unit": alert.unit,
                    },
                    priority=priority,
                )
                results["fcm"] = fcm_result
        
        # Telegram: Send to configured chat (critical alerts always)
        if self.telegram_enabled and alert.level in ("critical", "warning", "predictive"):
            telegram_result = await self.send_telegram_alert(alert)
            results["telegram"] = telegram_result
        
        # WebSocket: Broadcast to connected clients (handled by WebSocket service)
        results["websocket"] = {"success": True, "broadcast": True}
        
        # Audit log
        from app.services.audit import get_audit_service
        audit = get_audit_service()
        await audit.log(
            actor_id="system",
            actor_role="system",
            action="send_notification",
            resource_type="alert",
            resource_id=alert.id,
            details={
                "level": alert.level,
                "channels": list(results.keys()),
                "results": {k: v.get("success", False) for k, v in results.items()},
            },
        )
        
        return results
    
    async def notify_critical_alert(self, alert: AlertPublic) -> Dict[str, Any]:
        """Send critical alert with maximum urgency."""
        # Override priority for critical
        results = {}
        
        # FCM with critical priority
        if self.fcm_enabled:
            all_tokens = await self._get_all_fcm_tokens()
            if all_tokens:
                fcm_result = await self.send_fcm(
                    tokens=list(set(all_tokens)),
                    title=f"🔴 CRITICAL: {alert.parameter.replace('_', ' ').title()}",
                    body=f"Zone {alert.zone_id}: {alert.value:.1f} {alert.unit} - IMMEDIATE ACTION REQUIRED",
                    data={
                        "alert_id": alert.id,
                        "zone_id": alert.zone_id,
                        "parameter": alert.parameter,
                        "level": "critical",
                        "value": str(alert.value),
                        "unit": alert.unit,
                        "priority": "critical",
                    },
                    priority=NotificationPriority.CRITICAL,
                )
                results["fcm"] = fcm_result
        
        # Telegram with high visibility
        if self.telegram_enabled:
            telegram_result = await self.send_telegram_alert(alert)
            results["telegram"] = telegram_result
        
        # Audit
        from app.services.audit import get_audit_service
        audit = get_audit_service()
        await audit.log(
            actor_id="system",
            actor_role="system",
            action="send_critical_notification",
            resource_type="alert",
            resource_id=alert.id,
            details={"channels": list(results.keys())},
        )
        
        return results
    
    async def _get_all_fcm_tokens(self) -> List[str]:
        """Get all active FCM tokens from user preferences."""
        db = get_database()
        tokens = []
        
        cursor = db[Collections.USERS].find(
            {"notification_preferences.fcm_tokens": {"$exists": True, "$ne": []}},
            {"notification_preferences.fcm_tokens": 1}
        )
        
        async for doc in cursor:
            prefs = doc.get("notification_preferences", {})
            user_tokens = prefs.get("fcm_tokens", [])
            tokens.extend(user_tokens)
        
        return tokens
    
    # ============================================
    # User Preference Management
    # ============================================
    
    async def add_fcm_token(self, user_id: str, token: str) -> bool:
        """Add FCM token for user."""
        db = get_database()
        from bson import ObjectId
        
        result = await db[Collections.USERS].update_one(
            {"_id": ObjectId(user_id)},
            {"$addToSet": {"notification_preferences.fcm_tokens": token}}
        )
        return result.modified_count > 0
    
    async def remove_fcm_token(self, user_id: str, token: str) -> bool:
        """Remove FCM token for user."""
        db = get_database()
        from bson import ObjectId
        
        result = await db[Collections.USERS].update_one(
            {"_id": ObjectId(user_id)},
            {"$pull": {"notification_preferences.fcm_tokens": token}}
        )
        return result.modified_count > 0
    
    async def set_telegram_chat_id(self, user_id: str, chat_id: str) -> bool:
        """Set Telegram chat ID for user."""
        db = get_database()
        from bson import ObjectId
        
        result = await db[Collections.USERS].update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"notification_preferences.telegram_chat_id": chat_id}}
        )
        return result.modified_count > 0
    
    async def get_notification_status(self) -> Dict[str, Any]:
        """Get notification service status."""
        return {
            "fcm": {
                "enabled": self.fcm_enabled,
                "project_id": self.fcm_project_id,
            },
            "telegram": {
                "enabled": self.telegram_enabled,
                "chat_id_configured": bool(self.telegram_chat_id),
            },
        }


_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get singleton NotificationService instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service