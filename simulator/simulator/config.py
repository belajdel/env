"""Configuration for the MQTT simulator.

Values come from the process environment first, then from the repository
``.env`` file. Keep variable names identical to ``.env.example`` and the
backend so one file configures the whole local stack.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_ZONES_FILE = PROJECT_ROOT / "simulator" / "config" / "zones.yaml"
DEFAULT_SCENARIOS_FILE = PROJECT_ROOT / "simulator" / "config" / "scenarios.yaml"

# Frozen in docs/04-mqtt-spec.md §1 — do not edit without updating the docs.
ZONE_IDS = (
    "prod-01",
    "prod-02",
    "prod-03",
    "store-01",
    "store-02",
    "tech-01",
    "tech-02",
)


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE file without adding a python-dotenv dependency."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _password_var(zone_id: str) -> str:
    return "MQTT_DEVICE_PASSWORD_" + zone_id.upper().replace("-", "_")


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    """Runtime settings for one simulator process."""

    mqtt_host: str
    mqtt_port: int
    ca_cert: Path
    keepalive_s: int
    interval_s: float
    seed: int
    device_passwords: dict[str, str] = field(default_factory=dict)
    simulator_user: str = "simulator"
    simulator_password: str = ""
    zones_file: Path = DEFAULT_ZONES_FILE
    scenarios_file: Path = DEFAULT_SCENARIOS_FILE

    @property
    def shared_credentials(self) -> bool:
        """True when at least one device password is missing (demo fallback)."""
        return any(not self.device_passwords.get(zone) for zone in ZONE_IDS)

    def credentials_for(self, zone_id: str) -> tuple[str, str, bool]:
        """Return ``(username, password, per_device)`` for a zone."""
        password = self.device_passwords.get(zone_id, "")
        if password:
            return f"esp32-{zone_id}", password, True
        return self.simulator_user, self.simulator_password, False


def load_settings(env_file: Path | None = None) -> Settings:
    """Build settings from ``.env`` plus real environment overrides."""
    file_values = _load_dotenv(env_file or DEFAULT_ENV_FILE)

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key, file_values.get(key, default))

    ca_value = get("MQTT_CA_CERT", "infra/tls/certs/ca.crt")
    device_passwords = {zone: get(_password_var(zone)) for zone in ZONE_IDS}

    return Settings(
        mqtt_host=get("MQTT_HOST", "localhost"),
        mqtt_port=int(get("MQTT_PORT", "8883")),
        ca_cert=_resolve_path(ca_value),
        keepalive_s=int(get("MQTT_KEEPALIVE_S", "30")),
        interval_s=float(get("SIM_INTERVAL_S", "10")),
        seed=int(get("SIM_SEED", "42")),
        device_passwords={k: v for k, v in device_passwords.items() if v},
        simulator_user=get("MQTT_SIMULATOR_USER", "simulator"),
        simulator_password=get("MQTT_SIMULATOR_PASSWORD", ""),
        zones_file=_resolve_path(get("SIM_ZONES_FILE", str(DEFAULT_ZONES_FILE))),
        scenarios_file=_resolve_path(get("SIM_SCENARIOS_FILE", str(DEFAULT_SCENARIOS_FILE))),
    )
