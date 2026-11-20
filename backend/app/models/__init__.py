"""
Pydantic Models for Environmental Monitoring Platform
"""

from .user import User, UserCreate, UserUpdate, UserInDB, UserPublic, Token, TokenPayload
from .zone import Zone, ZoneCreate, ZoneUpdate, ZoneInDB
from .device import Device, DeviceCreate, DeviceUpdate, DeviceInDB, DeviceStatus
from .measurement import Measurement, MeasurementCreate, MeasurementInDB, MeasurementAggregate
from .alert import AlertRule, AlertRuleCreate, AlertRuleUpdate, AlertRuleInDB, Alert, AlertCreate, AlertUpdate, AlertInDB, AlertLevel, AlertStatus
from .report import Report, ReportCreate, ReportInDB, ReportType, ReportFormat
from .audit import AuditLog, AuditLogCreate, AuditLogInDB
from .ai import AIPrediction, AIPredictionInDB, RiskScore, RiskScoreInDB
from .websocket import WSMessage, WSMeasurementMessage, WSAlertMessage, WSConnectionInfo

__all__ = [
    # User
    "User", "UserCreate", "UserUpdate", "UserInDB", "UserPublic", "Token", "TokenPayload",
    # Zone
    "Zone", "ZoneCreate", "ZoneUpdate", "ZoneInDB",
    # Device
    "Device", "DeviceCreate", "DeviceUpdate", "DeviceInDB", "DeviceStatus",
    # Measurement
    "Measurement", "MeasurementCreate", "MeasurementInDB", "MeasurementAggregate",
    # Alert
    "AlertRule", "AlertRuleCreate", "AlertRuleUpdate", "AlertRuleInDB",
    "Alert", "AlertCreate", "AlertUpdate", "AlertInDB", "AlertLevel", "AlertStatus",
    # Report
    "Report", "ReportCreate", "ReportInDB", "ReportType", "ReportFormat",
    # Audit
    "AuditLog", "AuditLogCreate", "AuditLogInDB",
    # AI
    "AIPrediction", "AIPredictionInDB", "RiskScore", "RiskScoreInDB",
    # WebSocket
    "WSMessage", "WSMeasurementMessage", "WSAlertMessage", "WSConnectionInfo",
]