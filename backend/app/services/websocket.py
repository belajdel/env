"""
WebSocket Service
Real-time measurements, alerts, and device status via JWT-authenticated WebSocket.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from pymongo import ASCENDING

from app.core.config import settings
from app.core.database import get_database, Collections
from app.core.logging import get_logger
from app.services.auth import get_auth_service
from app.services.rbac import get_rbac_service
from app.models.websocket import (
    WSMessage, WSMessageType, WSMeasurementMessage, WSAlertMessage,
    WSDeviceStatusMessage, WSRiskScoreMessage, WSAIPredictionMessage,
    WSAuthMessage, WSAuthOKMessage, WSAuthErrorMessage,
    WSHeartbeatMessage, WSHeartbeatAckMessage,
    WSSubscribeMessage, WSSubscriptionOKMessage,
    WSRelayCommandMessage, WSRelayStateMessage, WSErrorMessage,
    WSConnectionInfo
)
from app.models.measurement import MeasurementPublic
from app.models.alert import AlertPublic

logger = get_logger(__name__)


@dataclass
class WSConnection:
    """WebSocket connection state."""
    connection_id: str
    websocket: WebSocket
    user_id: str
    username: str
    role: str
    connected_at: datetime
    last_heartbeat: datetime
    subscriptions: Set[str] = field(default_factory=set)
    zones: List[str] = field(default_factory=list)
    authenticated: bool = False


class WebSocketManager:
    """Manages WebSocket connections and message broadcasting."""
    
    def __init__(self):
        self.connections: Dict[str, WSConnection] = {}
        self._user_connections: Dict[str, Set[str]] = defaultdict(set)  # user_id -> connection_ids
        self._zone_subscribers: Dict[str, Set[str]] = defaultdict(set)  # channel -> connection_ids
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_failed": 0,
            "auth_failures": 0,
        }
    
    async def start(self) -> None:
        """Start heartbeat task."""
        if self._running:
            return
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("websocket_manager_started")
    
    async def stop(self) -> None:
        """Stop heartbeat task and close all connections."""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for conn in list(self.connections.values()):
            try:
                await conn.websocket.close(code=1001, reason="Server shutting down")
            except Exception:
                pass
        
        self.connections.clear()
        self._user_connections.clear()
        self._zone_subscribers.clear()
        logger.info("websocket_manager_stopped")
    
    async def connect(self, websocket: WebSocket, token: str) -> Optional[WSConnection]:
        """Accept connection and authenticate."""
        auth_service = get_auth_service()
        rbac = get_rbac_service()
        
        try:
            token_data = auth_service.verify_token(token)
        except ValueError as e:
            self._stats["auth_failures"] += 1
            await websocket.close(code=4001, reason=str(e))
            return None
        
        # Check max connections per user
        user_conns = self._user_connections.get(token_data.user_id, set())
        if len(user_conns) >= settings.WS_MAX_CONNECTIONS_PER_USER:
            await websocket.close(code=4002, reason="Max connections per user reached")
            return None
        
        # Get user's accessible zones
        zones = await self._get_user_zones(token_data.user_id, token_data.role, rbac)
        
        connection_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc)
        
        connection = WSConnection(
            connection_id=connection_id,
            websocket=websocket,
            user_id=token_data.user_id,
            username=token_data.username,
            role=token_data.role,
            connected_at=now,
            last_heartbeat=now,
            zones=zones,
            authenticated=True,
        )
        
        self.connections[connection_id] = connection
        self._user_connections[token_data.user_id].add(connection_id)
        
        self._stats["total_connections"] += 1
        self._stats["active_connections"] = len(self.connections)
        
        logger.info("websocket_connected", 
                    connection_id=connection_id, 
                    user_id=token_data.user_id,
                    zones=len(zones))
        
        # Send auth OK
        await self._send_message(connection, WSAuthOKMessage(
            type=WSMessageType.AUTH_OK,
            user_id=token_data.user_id,
            username=token_data.username,
            role=token_data.role,
            permissions=rbac.get_user_permissions(token_data.role),
        ))
        
        return connection
    
    async def disconnect(self, connection_id: str) -> None:
        """Disconnect and cleanup."""
        connection = self.connections.pop(connection_id, None)
        if not connection:
            return
        
        # Remove from user connections
        user_conns = self._user_connections.get(connection.user_id, set())
        user_conns.discard(connection_id)
        if not user_conns:
            self._user_connections.pop(connection.user_id, None)
        
        # Remove from zone subscribers
        for channel in connection.subscriptions:
            self._zone_subscribers[channel].discard(connection_id)
            if not self._zone_subscribers[channel]:
                self._zone_subscribers.pop(channel, None)
        
        self._stats["active_connections"] = len(self.connections)
        logger.info("websocket_disconnected", connection_id=connection_id)
    
    async def _get_user_zones(self, user_id: str, role: str, rbac) -> List[str]:
        """Get zones accessible to user."""
        db = get_database()
        if rbac.has_permission(role, "zone:read"):
            # Admin/operator/analyst can see all zones
            cursor = db[Collections.ZONES].find({}, {"zone_id": 1})
            return [doc["zone_id"] async for doc in cursor]
        else:
            # Maintenance might have limited access
            return []
    
    async def handle_message(self, connection_id: str, message: dict) -> None:
        """Handle incoming WebSocket message."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        try:
            msg_type = message.get("type")
            
            if msg_type == WSMessageType.HEARTBEAT:
                await self._handle_heartbeat(connection)
            
            elif msg_type == WSMessageType.SUBSCRIBE:
                await self._handle_subscribe(connection, message)
            
            elif msg_type == WSMessageType.UNSUBSCRIBE:
                await self._handle_unsubscribe(connection, message)
            
            elif msg_type == WSMessageType.RELAY_COMMAND:
                await self._handle_relay_command(connection, message)
            
            else:
                await self._send_error(connection, "UNKNOWN_MESSAGE_TYPE", f"Unknown message type: {msg_type}")
                
        except Exception as e:
            logger.error("websocket_message_error", connection_id=connection_id, error=str(e))
            await self._send_error(connection, "MESSAGE_ERROR", str(e))
    
    async def _handle_heartbeat(self, connection: WSConnection) -> None:
        """Handle heartbeat."""
        connection.last_heartbeat = datetime.now(timezone.utc)
        await self._send_message(connection, WSHeartbeatAckMessage(
            type=WSMessageType.HEARTBEAT_ACK,
        ))
    
    async def _handle_subscribe(self, connection: WSConnection, message: dict) -> None:
        """Handle subscription request."""
        channels = message.get("channels", [])
        subscribed = []
        
        for channel in channels:
            if await self._can_subscribe(connection, channel):
                connection.subscriptions.add(channel)
                self._zone_subscribers[channel].add(connection.connection_id)
                subscribed.append(channel)
            else:
                await self._send_error(connection, "SUBSCRIPTION_DENIED", f"Cannot subscribe to {channel}")
        
        if subscribed:
            await self._send_message(connection, WSSubscriptionOKMessage(
                type=WSMessageType.SUBSCRIPTION_OK,
                channels=subscribed,
            ))
    
    async def _handle_unsubscribe(self, connection: WSConnection, message: dict) -> None:
        """Handle unsubscribe request."""
        channels = message.get("channels", [])
        
        for channel in channels:
            connection.subscriptions.discard(channel)
            self._zone_subscribers[channel].discard(connection.connection_id)
            if not self._zone_subscribers[channel]:
                self._zone_subscribers.pop(channel, None)
    
    async def _can_subscribe(self, connection: WSConnection, channel: str) -> bool:
        """Check if connection can subscribe to channel."""
        # Channel format: "measurements:prod-01", "alerts:*", "devices:tech-01"
        parts = channel.split(":", 1)
        if len(parts) != 2:
            return False
        
        topic, target = parts
        valid_topics = ["measurements", "alerts", "devices", "risk", "predictions", "*"]
        
        if topic not in valid_topics:
            return False
        
        # Check zone access
        if target != "*" and target not in connection.zones:
            return False
        
        # Check permission based on topic
        permission_map = {
            "measurements": "measurement:read",
            "alerts": "alert:read",
            "devices": "device:read",
            "risk": "ai:risk",
            "predictions": "ai:predict",
        }
        
        if topic in permission_map:
            rbac = get_rbac_service()
            return rbac.has_permission(connection.role, permission_map[topic])
        
        return True
    
    async def _handle_relay_command(self, connection: WSConnection, message: dict) -> None:
        """Handle relay control command."""
        rbac = get_rbac_service()
        
        zone_id = message.get("zone_id")
        relay_id = message.get("relay_id")
        command = message.get("command")
        
        if not all([zone_id, relay_id, command]):
            await self._send_error(connection, "INVALID_RELAY_COMMAND", "Missing required fields")
            return
        
        # Check permission
        if not rbac.check_permission(connection.role, "relay:control", zone_id):
            await self._send_error(connection, "PERMISSION_DENIED", "No relay control permission")
            return
        
        # Forward to MQTT service
        from app.services.mqtt_ingestion import get_mqtt_service
        mqtt_service = get_mqtt_service()
        
        success = await mqtt_service.publish_relay_command(zone_id, relay_id, command)
        
        if success:
            # Acknowledge command
            await self._send_message(connection, WSRelayStateMessage(
                type=WSMessageType.RELAY_STATE,
                zone_id=zone_id,
                relay_id=relay_id,
                state=command in ("on", "toggle"),
                timestamp=datetime.now(timezone.utc),
            ))
        else:
            await self._send_error(connection, "RELAY_COMMAND_FAILED", "MQTT publish failed")
    
    async def _send_message(self, connection: WSConnection, message: WSMessage) -> bool:
        """Send message to a single connection."""
        try:
            await connection.websocket.send_text(message.model_dump_json())
            self._stats["messages_sent"] += 1
            return True
        except Exception as e:
            self._stats["messages_failed"] += 1
            logger.warning("websocket_send_failed", connection_id=connection.connection_id, error=str(e))
            # Schedule disconnect
            asyncio.create_task(self.disconnect(connection.connection_id))
            return False
    
    async def _send_error(self, connection: WSConnection, code: str, message: str) -> None:
        """Send error message."""
        await self._send_message(connection, WSErrorMessage(
            type=WSMessageType.ERROR,
            code=code,
            message=message,
        ))
    
    # ============================================
    # Broadcast Methods (called by other services)
    # ============================================
    
    async def broadcast_measurement(self, measurement: MeasurementPublic) -> int:
        """Broadcast measurement to subscribed connections."""
        channel = f"measurements:{measurement.zone_id}"
        return await self._broadcast_to_channel(channel, WSMeasurementMessage(
            type=WSMessageType.MEASUREMENT,
            data=measurement,
        ))
    
    async def broadcast_alert(self, alert: AlertPublic) -> int:
        """Broadcast alert to subscribed connections."""
        channel = f"alerts:{alert.zone_id}"
        return await self._broadcast_to_channel(channel, WSAlertMessage(
            type=WSMessageType.ALERT,
            data=alert,
        ))
    
    async def broadcast_alert_update(self, alert_id: str, status: str, updated_by: str) -> int:
        """Broadcast alert status update."""
        channel = "alerts:*"  # Global alert updates
        return await self._broadcast_to_channel(channel, WSAlertUpdateMessage(
            type=WSMessageType.ALERT_UPDATE,
            alert_id=alert_id,
            status=status,
            updated_by=updated_by,
            updated_at=datetime.now(timezone.utc),
        ))
    
    async def broadcast_device_status(self, device_id: str, zone_id: str, status: str) -> int:
        """Broadcast device status change."""
        channel = f"devices:{zone_id}"
        return await self._broadcast_to_channel(channel, WSDeviceStatusMessage(
            type=WSMessageType.DEVICE_STATUS,
            device_id=device_id,
            zone_id=zone_id,
            status=status,
            timestamp=datetime.now(timezone.utc),
        ))
    
    async def broadcast_risk_score(self, zone_id: str, score: int, level: str, factors: dict) -> int:
        """Broadcast risk score update."""
        channel = f"risk:{zone_id}"
        return await self._broadcast_to_channel(channel, WSRiskScoreMessage(
            type=WSMessageType.RISK_SCORE,
            zone_id=zone_id,
            score=score,
            level=level,
            factors=factors,
        ))
    
    async def broadcast_ai_prediction(self, zone_id: str, prediction_type: str, 
                                      horizon_minutes: int, value: float, confidence: float) -> int:
        """Broadcast AI prediction."""
        channel = f"predictions:{zone_id}"
        return await self._broadcast_to_channel(channel, WSAIPredictionMessage(
            type=WSMessageType.AI_PREDICTION,
            zone_id=zone_id,
            prediction_type=prediction_type,
            horizon_minutes=horizon_minutes,
            value=value,
            confidence=confidence,
        ))
    
    async def _broadcast_to_channel(self, channel: str, message: WSMessage) -> int:
        """Broadcast message to all connections subscribed to channel."""
        connection_ids = self._zone_subscribers.get(channel, set())
        if not connection_ids:
            return 0
        
        sent = 0
        for conn_id in list(connection_ids):  # Copy to avoid modification during iteration
            connection = self.connections.get(conn_id)
            if connection and connection.authenticated:
                if await self._send_message(connection, message):
                    sent += 1
        
        return sent
    
    async def _heartbeat_loop(self) -> None:
        """Send heartbeat to all connections periodically."""
        while self._running:
            try:
                await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)
                
                now = datetime.now(timezone.utc)
                stale_connections = []
                
                for conn_id, connection in self.connections.items():
                    # Check for stale connections
                    if (now - connection.last_heartbeat).total_seconds() > settings.WS_HEARTBEAT_INTERVAL * 3:
                        stale_connections.append(conn_id)
                    else:
                        # Send heartbeat
                        await self._send_message(connection, WSHeartbeatMessage(
                            type=WSMessageType.HEARTBEAT,
                        ))
                
                # Disconnect stale connections
                for conn_id in stale_connections:
                    logger.info("websocket_stale_disconnect", connection_id=conn_id)
                    await self.disconnect(conn_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("websocket_heartbeat_error", error=str(e))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket manager statistics."""
        return {
            **self._stats,
            "connections_by_role": self._count_by_role(),
            "subscriptions": {k: len(v) for k, v in self._zone_subscribers.items()},
        }
    
    def _count_by_role(self) -> Dict[str, int]:
        counts = defaultdict(int)
        for conn in self.connections.values():
            counts[conn.role] += 1
        return dict(counts)
    
    def get_connection_info(self) -> List[WSConnectionInfo]:
        """Get info about all connections."""
        return [
            WSConnectionInfo(
                connection_id=c.connection_id,
                user_id=c.user_id,
                username=c.username,
                role=c.role,
                connected_at=c.connected_at,
                last_heartbeat=c.last_heartbeat,
                subscriptions=list(c.subscriptions),
                zones=c.zones,
            )
            for c in self.connections.values()
        ]


_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get singleton WebSocketManager instance."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager