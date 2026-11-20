"""The simulator must publish exactly the payloads defined in docs/04-mqtt-spec.md."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from simulator.config import ZONE_IDS
from simulator.profiles import PARAMETERS, RANGES, UNITS, load_zones
from simulator.publisher import (
    lwt_payload,
    measurement_payload,
    state_payload,
    status_payload,
)

ZONES_FILE = Path(__file__).resolve().parents[1] / "config" / "zones.yaml"
WHEN = datetime(2026, 11, 20, 10, 15, 30, 120000, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def profiles():
    return {profile.zone_id: profile for profile in load_zones(ZONES_FILE)}


def test_measurement_payload_matches_the_contract(profiles):
    profile = profiles["prod-01"]
    payload = measurement_payload(
        profile.zone_id, profile.device_id, "temperature", 31.4, WHEN, 18422
    )
    assert set(payload) == {
        "schema_version",
        "zone_id",
        "device_id",
        "parameter",
        "value",
        "unit",
        "timestamp",
        "seq",
        "quality",
        "source",
    }
    assert payload["schema_version"] == 1
    assert payload["zone_id"] == "prod-01"
    assert payload["device_id"] == "esp32-prod-01"
    assert payload["parameter"] == "temperature"
    assert payload["unit"] == "°C"
    assert payload["timestamp"] == "2026-11-20T10:15:30.120Z"
    assert payload["seq"] == 18422
    assert payload["quality"] == "good"
    assert payload["source"] == "simulator"


def test_every_parameter_uses_its_canonical_unit(profiles):
    profile = profiles["tech-01"]
    for parameter in PARAMETERS:
        payload = measurement_payload(profile.zone_id, profile.device_id, parameter, 1, WHEN, 1)
        assert payload["unit"] == UNITS[parameter]


def test_timestamp_is_rfc3339_utc_with_milliseconds(profiles):
    profile = profiles["store-01"]
    payload = measurement_payload(profile.zone_id, profile.device_id, "pm25", 12, WHEN, 7)
    value = payload["timestamp"]
    assert value.endswith("Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed == WHEN
    assert parsed.tzinfo is timezone.utc


def test_payload_survives_a_json_round_trip(profiles):
    profile = profiles["prod-03"]
    payload = measurement_payload(
        profile.zone_id, profile.device_id, "noise", 84.2, WHEN, 99, "suspect"
    )
    assert json.loads(json.dumps(payload)) == payload


def test_values_stay_within_the_accepted_range():
    for zone_id in ZONE_IDS:
        assert zone_id in ZONE_IDS
    for parameter, (low, high) in RANGES.items():
        assert low < high
        assert parameter in PARAMETERS


def test_status_payload_is_retained_friendly(profiles):
    profile = profiles["prod-02"]
    payload = status_payload(
        profile.zone_id, profile.device_id, "online", "heartbeat", WHEN, uptime_s=86400
    )
    assert payload["status"] == "online"
    assert payload["reason"] == "heartbeat"
    assert payload["uptime_s"] == 86400
    assert payload["buffered_samples"] == 0
    assert payload["timestamp"].endswith("Z")


def test_lwt_payload_has_no_timestamp(profiles):
    profile = profiles["store-02"]
    payload = lwt_payload(profile.zone_id, profile.device_id)
    assert payload == {
        "schema_version": 1,
        "zone_id": "store-02",
        "device_id": "esp32-store-02",
        "status": "offline",
        "reason": "lwt",
    }
    assert "timestamp" not in payload


def test_state_payload_matches_the_contract(profiles):
    profile = profiles["tech-02"]
    relays = {
        "1": {"state": "off", "mode": "auto"},
        "2": {"state": "on", "mode": "manual"},
    }
    payload = state_payload(
        profile.zone_id, profile.device_id, relays, WHEN, "T:24.5C H:46%", "AQ:520 PM2.5:7"
    )
    assert payload["relays"] == relays
    assert set(payload["leds"]) == {"green", "orange", "red"}
    assert set(payload["sensor_health"]) == set(PARAMETERS)
    assert payload["lcd"]["line1"].startswith("T:")
    assert set(payload) == {
        "schema_version",
        "zone_id",
        "device_id",
        "relays",
        "leds",
        "lcd",
        "sensor_health",
        "timestamp",
    }
