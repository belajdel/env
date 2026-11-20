"""
WebSocket Models
"""

from datetime import datetime
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

from .measurement import MeasurementPublic, VALID_PARAMETERS
from .alert import AlertPublic, ALERT_LEVELS, ALERT_STATUSES


class WSMessageType(str, Enum):
    """WebSocket message types."""
    # Connection
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    AUTH = "auth"
    AUTH_OK = "auth_ok"
    AUTH_ERROR = "auth_error"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat_ack"
    ERROR = "error"
    
    # Subscriptions
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    SUBSCRIPTION_OK = "subscription_ok"
    
    # Data
    MEASUREMENT = "measurement"
    MEASUREMENT_BATCH = "measurement_batch"
    ALERT = "alert"
    ALERT_UPDATE = "alert_update"
    DEVICE_STATUS = "device_status"
    RISK_SCORE = "risk_score"
    AI_PREDICTION = "ai_prediction"
    
    # Control
    RELAY_COMMAND = "relay_command"
    RELAY_STATE = "relay_state"


class WSMessageBase(BaseModel):
    """Base WebSocket message."""
    type: WSMessageType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


class WSConnectMessage(WSMessageBase):
    """Client connection message."""
    type: Literal[WSMessageType.CONNECT] = WSMessageType.CONNECT
    client_info: Optional[Dict[str, Any]] = None


class WSAuthMessage(WSMessageBase):
    """Authentication message."""
    type: Literal[WSMessageType.AUTH] = WSMessageType.AUTH
    token: str


class WSAuthOKMessage(WSMessageBase):
    """Authentication success."""
    type: Literal[WSMessageType.AUTH_OK] = WSMessageType.AUTH_OK
    user_id: str
    username: str
    role: str
    permissions: List[str]


class WSAuthErrorMessage(WSMessageBase):
    """Authentication error."""
    type: Literal[WSMessageType.AUTH_ERROR] = WSMessageType.AUTH_ERROR
    error: str


class WSHeartbeatMessage(WSMessageBase):
    """Heartbeat message."""
    type: Literal[WSMessageType.HEARTBEAT] = WSMessageType.HEARTBEAT


class WSHeartbeatAckMessage(WSMessageBase):
    """Heartbeat acknowledgment."""
    type: Literal[WSMessageType.HEARTBEAT_ACK] = WSMessageType.HEARTBEAT_ACK


class WSSubscribeMessage(WSMessageBase):
    """Subscription message."""
    type: Literal[WSMessageType.SUBSCRIBE] = WSMessageType.SUBSCRIBE
    channels: List[str]  # e.g., ["measurements:prod-01", "alerts:*"]


class WSSubscriptionOKMessage(WSMessageBase):
    """Subscription confirmation."""
    type: Literal[WSMessageType.SUBSCRIPTION_OK] = WSMessageType.SUBSCRIPTION_OK
    channels: List[str]


class WSMeasurementMessage(WSMessageBase):
    """Real-time measurement message."""
    type: Literal[WSMessageType.MEASUREMENT] = WSMessageType.MEASUREMENT
    data: MeasurementPublic


class WSMeasurementBatchMessage(WSMessageBase):
    """Batch of measurements."""
    type: Literal[WSMessageType.MEASUREMENT_BATCH] = WSMessageType.MEASUREMENT_BATCH
    data: List[MeasurementPublic]


class WSAlertMessage(WSMessageBase):
    """New alert message."""
    type: Literal[WSMessageType.ALERT] = WSMessageType.ALERT
    data: AlertPublic


class WSAlertUpdateMessage(WSMessageBase):
    """Alert status update."""
    type: Literal[WSMessageType.ALERT_UPDATE] = WSMessageType.ALERT_UPDATE
    alert_id: str
    status: ALERT_STATUSES
    updated_by: str
    updated_at: datetime


class WSDeviceStatusMessage(WSMessageBase):
    """Device status update."""
    type: Literal[WSMessageType.DEVICE_STATUS] = WSMessageType.DEVICE_STATUS
    device_id: str
    zone_id: str
    status: Literal["online", "offline", "error", "maintenance"]
    timestamp: datetime


class WSRiskScoreMessage(WSMessageBase):
    """Risk score update."""
    type: Literal[WSMessageType.RISK_SCORE] = WSMessageType.RISK_SCORE
    zone_id: str
    score: int
    level: str
    factors: Dict[str, float]


class WSAIPredictionMessage(WSMessageBase):
    """AI prediction message."""
    type: Literal[WSMessageType.AI_PREDICTION] = WSMessageType.AI_PREDICTION
    zone_id: str
    prediction_type: str
    horizon_minutes: int
    value: float
    confidence: float


class WSRelayCommandMessage(WSMessageBase):
    """Relay control command (dashboard -> backend)."""
    type: Literal[WSMessageType.RELAY_COMMAND] = WSMessageType.RELAY_COMMAND
    zone_id: str
    relay_id: int
    command: Literal["on", "off", "toggle", "state"]


class WSRelayStateMessage(WSMessageBase):
    """Relay state update (backend -> dashboard)."""
    type: Literal[WSMessageType.RELAY_STATE] = WSMessageType.RELAY_STATE
    zone_id: str
    relay_id: int
    state: bool
    timestamp: datetime


class WSErrorMessage(WSMessageBase):
    """Error message."""
    type: Literal[WSMessageType.ERROR] = WSMessageType.ERROR
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


# Union type for all WS messages
WSMessage = (
    WSConnectMessage | WSAuthMessage | WSAuthOKMessage | WSAuthErrorMessage |
    WSHeartbeatMessage | WSHeartbeatAckMessage |
    WSSubscribeMessage | WSSubscriptionOKMessage |
    WSMeasurementMessage | WSMeasurementBatchMessage |
    WSAlertMessage | WSAlertUpdateMessage |
    WSDeviceStatusMessage | WSRiskScoreMessage | WSAIPredictionMessage |
    WSRelayCommandMessage | WSRelayStateMessage | WSErrorMessage
)


class WSConnectionInfo(BaseModel):
    """WebSocket connection info for management."""
    connection_id: str
    user_id: str
    username: str
    role: str
    connected_at: datetime
    last_heartbeat: datetime
    subscriptions: List[str]
    zones: List[str]  # zones user has access to