"""MQTT 3.1.1 / TLS publisher with firmware-identical payloads.

One paho client is used per device when per-device credentials exist, so status,
LWT and retained state behave exactly like real hardware. If device passwords are
missing the simulator falls back to the single ``simulator`` demo account.
"""

from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping

import paho.mqtt.client as mqtt

from .anomalies import AnomalyEngine
from .config import Settings
from .profiles import PARAMETERS, UNITS, ZoneProfile, generate

LOGGER = logging.getLogger(__name__)

FIRMWARE_VERSION = "sim-0.1.0"
SCHEMA_VERSION = 1
MAX_RECENT_COMMANDS = 20


def iso_timestamp(when: datetime) -> str:
    """RFC 3339 UTC with millisecond precision, e.g. ``2026-11-20T10:15:30.120Z``."""
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + (
        f"{when.microsecond // 1000:03d}Z"
    )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def measurement_payload(
    zone_id: str,
    device_id: str,
    parameter: str,
    value: float,
    when: datetime,
    seq: int,
    quality: str = "good",
) -> dict[str, object]:
    """Build the measurement payload defined in docs/04-mqtt-spec.md §3."""
    return {
        "schema_version": SCHEMA_VERSION,
        "zone_id": zone_id,
        "device_id": device_id,
        "parameter": parameter,
        "value": value,
        "unit": UNITS[parameter],
        "timestamp": iso_timestamp(when),
        "seq": seq,
        "quality": quality,
        "source": "simulator",
    }


def status_payload(
    zone_id: str,
    device_id: str,
    status: str,
    reason: str,
    when: datetime | None,
    *,
    uptime_s: int = 0,
    rssi: int = -58,
    buffered_samples: int = 0,
) -> dict[str, object]:
    """Build the retained device status payload (docs/04-mqtt-spec.md §4)."""
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "zone_id": zone_id,
        "device_id": device_id,
        "status": status,
        "reason": reason,
        "firmware": FIRMWARE_VERSION,
        "ip": "127.0.0.1",
        "rssi": rssi,
        "uptime_s": uptime_s,
        "buffered_samples": buffered_samples,
    }
    if when is not None:
        payload["timestamp"] = iso_timestamp(when)
    return payload


def lwt_payload(zone_id: str, device_id: str) -> dict[str, object]:
    """Last-will payload: deliberately has no timestamp (docs/04-mqtt-spec.md §5)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "zone_id": zone_id,
        "device_id": device_id,
        "status": "offline",
        "reason": "lwt",
    }


def state_payload(
    zone_id: str,
    device_id: str,
    relays: Mapping[str, Mapping[str, str]],
    when: datetime,
    lcd_line1: str,
    lcd_line2: str,
) -> dict[str, object]:
    """Build the retained relay/LED/LCD snapshot (docs/04-mqtt-spec.md §6)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "zone_id": zone_id,
        "device_id": device_id,
        "relays": {
            relay_id: {"state": state["state"], "mode": state["mode"]}
            for relay_id, state in relays.items()
        },
        "leds": {"green": True, "orange": False, "red": False},
        "lcd": {"line1": lcd_line1, "line2": lcd_line2},
        "sensor_health": {parameter: "ok" for parameter in PARAMETERS},
        "timestamp": iso_timestamp(when),
    }


@dataclass
class _Session:
    """One MQTT connection, covering one device or every zone in shared mode."""

    client_id: str
    username: str
    password: str
    per_device: bool
    zones: tuple[str, ...]
    connected: threading.Event = field(default_factory=threading.Event)
    client: mqtt.Client | None = None


class SimulatorPublisher:
    """Publish simulated zones and answer relay commands like real firmware."""

    def __init__(
        self,
        settings: Settings,
        profiles: Iterable[ZoneProfile],
        engine: AnomalyEngine,
    ) -> None:
        self.settings = settings
        self.profiles = list(profiles)
        self.by_zone = {profile.zone_id: profile for profile in self.profiles}
        self.engine = engine
        self._sessions: list[_Session] = []
        self._session_by_zone: dict[str, _Session] = {}
        self._seq: dict[str, int] = {profile.zone_id: 0 for profile in self.profiles}
        self._last_values: dict[str, dict[str, float]] = {
            profile.zone_id: {} for profile in self.profiles
        }
        self._last_status_at: dict[str, float] = {}
        self._relays: dict[str, dict[str, dict[str, str]]] = {
            profile.zone_id: {
                "1": {"state": "off", "mode": "auto"},
                "2": {"state": "off", "mode": "manual"},
            }
            for profile in self.profiles
        }
        self._recent_commands: list[str] = []
        self._t0 = time.monotonic()
        self._started = False

    # -- lifecycle ---------------------------------------------------------
    def _build_sessions(self) -> list[_Session]:
        shared = self.settings.shared_credentials
        sessions: list[_Session] = []
        if shared:
            username = self.settings.simulator_user
            password = self.settings.simulator_password
            if not password:
                raise RuntimeError(
                    "no MQTT credentials: set MQTT_DEVICE_PASSWORD_* "
                    "or MQTT_SIMULATOR_PASSWORD in .env"
                )
            sessions.append(
                _Session(
                    client_id="sim-shared",
                    username=username,
                    password=password,
                    per_device=False,
                    zones=tuple(profile.zone_id for profile in self.profiles),
                )
            )
        else:
            for profile in self.profiles:
                username, password, per_device = self.settings.credentials_for(profile.zone_id)
                sessions.append(
                    _Session(
                        client_id=f"sim-{profile.device_id}",
                        username=username,
                        password=password,
                        per_device=per_device,
                        zones=(profile.zone_id,),
                    )
                )
        return sessions

    def start(self) -> None:
        """Connect every session and wait briefly for CONNACK."""
        if self._started:
            return
        if not self.settings.ca_cert.is_file():
            raise FileNotFoundError(
                f"CA certificate not found: {self.settings.ca_cert}. "
                "Run infra/tls/generate-certs.sh first."
            )

        self._sessions = self._build_sessions()
        for session in self._sessions:
            session.client = self._make_client(session)

        deadline = time.monotonic() + 10.0
        for session in self._sessions:
            remaining = max(0.0, deadline - time.monotonic())
            if not session.connected.wait(remaining):
                LOGGER.warning(
                    "no CONNACK yet",
                    extra={"client_id": session.client_id, "host": self.settings.mqtt_host},
                )
        self._started = True
        self._t0 = time.monotonic()

    def _make_client(self, session: _Session) -> mqtt.Client:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=session.client_id,
            clean_session=True,
            protocol=mqtt.MQTTv311,
            userdata=session,
        )
        client.username_pw_set(session.username, session.password)
        client.tls_set(
            ca_certs=str(self.settings.ca_cert),
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        for zone_id in session.zones:
            self._session_by_zone[zone_id] = session
        if session.per_device:
            zone_id = session.zones[0]
            device_id = self.by_zone[zone_id].device_id
            client.will_set(
                f"factory/{zone_id}/{device_id}/status",
                json.dumps(lwt_payload(zone_id, device_id)),
                qos=1,
                retain=True,
            )

        client.connect_async(
            self.settings.mqtt_host,
            self.settings.mqtt_port,
            keepalive=self.settings.keepalive_s,
        )
        client.loop_start()
        return client

    def stop(self) -> None:
        """Publish a clean offline status, then disconnect every session."""
        if not self._started:
            return
        now = datetime.now(timezone.utc)
        for session in self._sessions:
            if session.client is None or not session.connected.is_set():
                continue
            for zone_id in session.zones:
                profile = self.by_zone[zone_id]
                self._publish_json(
                    session,
                    f"factory/{zone_id}/{profile.device_id}/status",
                    status_payload(
                        zone_id,
                        profile.device_id,
                        "offline",
                        "shutdown",
                        now,
                        uptime_s=self._uptime_s(),
                    ),
                    retain=True,
                    wait=True,
                )
            session.client.disconnect()
            session.client.loop_stop()
        self._started = False

    def _uptime_s(self) -> int:
        return int(time.monotonic() - self._t0)

    # -- publishing --------------------------------------------------------
    def _publish_json(
        self,
        session: _Session,
        topic: str,
        payload: Mapping[str, object],
        *,
        retain: bool = False,
        wait: bool = False,
    ) -> bool:
        client = session.client
        if client is None:
            return False
        info = client.publish(topic, json.dumps(payload), qos=1, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.warning("publish failed", extra={"topic": topic, "rc": info.rc})
            return False
        if wait:
            try:
                info.wait_for_publish(timeout=2.0)
            except (ValueError, RuntimeError):
                LOGGER.warning("publish not confirmed", extra={"topic": topic})
                return False
        return True

    def tick(self, tick: int, when: datetime | None = None) -> int:
        """Publish one sample per healthy parameter for every selected zone."""
        now = when or datetime.now(timezone.utc)
        elapsed = time.monotonic() - self._t0
        published = 0

        for profile in self.profiles:
            session = self._session_by_zone.get(profile.zone_id)
            if session is None or not session.connected.is_set():
                continue

            self._seq[profile.zone_id] = (self._seq[profile.zone_id] + 1) & 0xFFFFFFFF
            seq = self._seq[profile.zone_id]
            values: dict[str, float] = {}

            for parameter in PARAMETERS:
                value = generate(
                    profile,
                    parameter,
                    now,
                    elapsed,
                    tick,
                    self.settings.seed,
                )
                adjusted = self.engine.apply(profile.zone_id, parameter, value, elapsed)
                if adjusted is None:
                    LOGGER.debug(
                        "sample dropped by anomaly",
                        extra={"zone_id": profile.zone_id, "parameter": parameter},
                    )
                    continue
                values[parameter] = adjusted
                stuck = self.engine.is_stuck(profile.zone_id, parameter, elapsed)
                quality = "suspect" if stuck else "good"
                payload = measurement_payload(
                    profile.zone_id,
                    profile.device_id,
                    parameter,
                    adjusted,
                    now,
                    seq,
                    quality,
                )
                if self._publish_json(
                    session, f"factory/{profile.zone_id}/{parameter}", payload
                ):
                    published += 1

            self._last_values[profile.zone_id] = values
            self._maybe_status(session, profile, now)
            self.engine.expire(elapsed)

        return published

    def _maybe_status(self, session: _Session, profile: ZoneProfile, now: datetime) -> None:
        last = self._last_status_at.get(profile.zone_id)
        if last is not None and (now.timestamp() - last) < 60:
            return
        self._last_status_at[profile.zone_id] = now.timestamp()
        self._publish_json(
            session,
            f"factory/{profile.zone_id}/{profile.device_id}/status",
            status_payload(
                profile.zone_id,
                profile.device_id,
                "online",
                "heartbeat",
                now,
                uptime_s=self._uptime_s(),
                rssi=-55 - (zlib_crc(profile.zone_id) % 12),
            ),
        )

    def publish_state(self, zone_id: str) -> None:
        """Publish the retained state snapshot for one zone."""
        session = self._session_by_zone.get(zone_id)
        profile = self.by_zone.get(zone_id)
        if session is None or profile is None or session.client is None:
            return
        values = self._last_values.get(zone_id, {})
        line1 = (
            f"T:{values.get('temperature', 0):.1f}C H:{values.get('humidity', 0):.0f}%"
            if values
            else "T:-- H:--"
        )
        line2 = (
            f"AQ:{values.get('air_quality', 0):.0f} PM2.5:{values.get('pm25', 0):.0f}"
            if values
            else "waiting for data"
        )
        self._publish_json(
            session,
            f"factory/{zone_id}/{profile.device_id}/state",
            state_payload(
                zone_id,
                profile.device_id,
                self._relays[zone_id],
                datetime.now(timezone.utc),
                line1,
                line2,
            ),
            retain=True,
            wait=True,
        )

    # -- MQTT callbacks ----------------------------------------------------
    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: _Session,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        session = userdata
        if reason_code.is_failure:
            LOGGER.error(
                "MQTT connection refused",
                extra={"client_id": session.client_id, "reason": str(reason_code)},
            )
            return

        session.connected.set()
        LOGGER.info(
            "MQTT connected",
            extra={
                "client_id": session.client_id,
                "username": session.username,
                "zones": list(session.zones),
            },
        )
        now = datetime.now(timezone.utc)
        for zone_id in session.zones:
            profile = self.by_zone[zone_id]
            self._publish_json(
                session,
                f"factory/{zone_id}/{profile.device_id}/status",
                status_payload(
                    zone_id,
                    profile.device_id,
                    "online",
                    "boot",
                    now,
                    uptime_s=self._uptime_s(),
                ),
                retain=True,
                wait=True,
            )
            if session.per_device:
                self.publish_state(zone_id)
            client.subscribe(f"factory/{zone_id}/{profile.device_id}/cmd", qos=1)
        self._last_status_at = {zone_id: now.timestamp() for zone_id in session.zones}

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: _Session,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        session = userdata
        session.connected.clear()
        LOGGER.warning(
            "MQTT disconnected",
            extra={"client_id": session.client_id, "reason": str(reason_code)},
        )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: _Session,
        message: mqtt.MQTTMessage,
    ) -> None:
        session = userdata
        parts = message.topic.split("/")
        if len(parts) != 4 or parts[0] != "factory" or parts[3] != "cmd":
            LOGGER.warning("unexpected command topic", extra={"topic": message.topic})
            return
        zone_id, device_id = parts[1], parts[2]
        profile = self.by_zone.get(zone_id)
        if profile is None or profile.device_id != device_id:
            LOGGER.warning("command for unknown device", extra={"topic": message.topic})
            return

        try:
            command = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            LOGGER.warning("invalid command JSON", extra={"topic": message.topic})
            return

        command_id = str(command.get("command_id", ""))
        relay = command.get("relay")
        state = command.get("state")
        status = "executed"
        reason: str | None = None

        try:
            expires_at = _parse_timestamp(str(command.get("expires_at", "")))
        except ValueError:
            expires_at = None

        if command.get("schema_version") != SCHEMA_VERSION or command.get("action") != "relay.set":
            status, reason = "rejected", "unsupported_command"
        elif relay not in (1, 2) or state not in ("on", "off"):
            status, reason = "rejected", "invalid_relay_or_state"
        elif expires_at is not None and expires_at < datetime.now(timezone.utc):
            status, reason = "rejected", "expired"
        elif command_id in self._recent_commands:
            status, reason = "executed", "duplicate"
        else:
            self._remember_command(command_id)
            relay_key = str(relay)
            self._relays[zone_id][relay_key]["state"] = state
            self._relays[zone_id][relay_key]["mode"] = "manual"
            self.publish_state(zone_id)

        ack = {
            "schema_version": SCHEMA_VERSION,
            "command_id": command_id,
            "status": status,
            "relay": relay,
            "state": state,
            "executed_at": iso_timestamp(datetime.now(timezone.utc)),
            "reason": reason,
        }
        self._publish_json(
            session,
            f"factory/{zone_id}/{device_id}/ack",
            ack,
            wait=True,
        )
        LOGGER.info(
            "relay command handled",
            extra={
                "zone_id": zone_id,
                "command_id": command_id,
                "status": status,
                "relay": relay,
                "state": state,
            },
        )

    def _remember_command(self, command_id: str) -> None:
        self._recent_commands.append(command_id)
        del self._recent_commands[:-MAX_RECENT_COMMANDS]


def zlib_crc(value: str) -> int:
    """Stable tiny hash so fake RSSI is deterministic per zone."""
    return zlib.crc32(value.encode("utf-8"))
