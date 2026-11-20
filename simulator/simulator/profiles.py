"""Zone profiles: deterministic daily cycles, slow drift and sensor noise.

Every value is a pure function of ``(zone, parameter, wall clock, elapsed time,
seed)``. There is no hidden random state, so two runs with the same seed produce
identical payloads — required for reproducible AI training data.
"""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

import yaml

from .config import ZONE_IDS

PARAMETERS: tuple[str, ...] = (
    "temperature",
    "humidity",
    "noise",
    "air_quality",
    "pm25",
    "pm10",
    "voltage",
)

UNITS: Mapping[str, str] = {
    "temperature": "°C",
    "humidity": "%",
    "noise": "dB(A)",
    "air_quality": "ppm",
    "pm25": "µg/m³",
    "pm10": "µg/m³",
    "voltage": "V AC",
}

# Accepted physical ranges from docs/04-mqtt-spec.md §3.
RANGES: Mapping[str, tuple[float, float]] = {
    "temperature": (-40.0, 125.0),
    "humidity": (0.0, 100.0),
    "noise": (30.0, 140.0),
    "air_quality": (0.0, 5000.0),
    "pm25": (0.0, 1000.0),
    "pm10": (0.0, 2000.0),
    "voltage": (0.0, 300.0),
}

DECIMALS: Mapping[str, int] = {
    "temperature": 1,
    "humidity": 1,
    "noise": 1,
    "air_quality": 0,
    "pm25": 0,
    "pm10": 0,
    "voltage": 1,
}

# Gaussian sigma of the per-sample noise.
NOISE_SIGMA: Mapping[str, float] = {
    "temperature": 0.18,
    "humidity": 1.1,
    "noise": 1.6,
    "air_quality": 14.0,
    "pm25": 2.2,
    "pm10": 3.4,
    "voltage": 0.55,
}

# Slow wear/drift per hour, capped so a long demo stays physically plausible.
DRIFT_PER_HOUR: Mapping[str, float] = {
    "temperature": 0.02,
    "humidity": 0.03,
    "noise": 0.05,
    "air_quality": 0.5,
    "pm25": 0.03,
    "pm10": 0.05,
    "voltage": 0.01,
}

MAX_DRIFT: Mapping[str, float] = {
    "temperature": 1.2,
    "humidity": 2.5,
    "noise": 2.0,
    "air_quality": 60.0,
    "pm25": 4.0,
    "pm10": 8.0,
    "voltage": 0.8,
}


class ProfileError(ValueError):
    """Raised when a zone profile file is invalid."""


@dataclass(frozen=True)
class ZoneProfile:
    """Static description of one simulated zone."""

    zone_id: str
    name: str
    zone_type: str
    device_id: str
    baselines: Mapping[str, float]
    diurnal: Mapping[str, float]

    def baseline(self, parameter: str) -> float:
        try:
            return float(self.baselines[parameter])
        except KeyError as exc:  # pragma: no cover - guarded at load time
            raise ProfileError(f"{self.zone_id}: missing baseline for {parameter}") from exc

    def amplitude(self, parameter: str) -> float:
        try:
            return float(self.diurnal[parameter])
        except KeyError as exc:  # pragma: no cover - guarded at load time
            raise ProfileError(f"{self.zone_id}: missing diurnal amplitude for {parameter}") from exc


_ZONE_TYPES = {"production", "storage", "technical"}


def load_zones(path: Path) -> list[ZoneProfile]:
    """Load and validate ``config/zones.yaml``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("zones")
    if not isinstance(entries, list) or not entries:
        raise ProfileError(f"{path}: expected a non-empty 'zones' list")

    profiles: list[ZoneProfile] = []
    seen: set[str] = set()
    for entry in entries:
        zone_id = str(entry.get("zone_id", "")).strip()
        if zone_id not in ZONE_IDS:
            raise ProfileError(f"{path}: unknown zone_id '{zone_id}'")
        if zone_id in seen:
            raise ProfileError(f"{path}: duplicate zone_id '{zone_id}'")
        seen.add(zone_id)

        zone_type = str(entry.get("type", ""))
        if zone_type not in _ZONE_TYPES:
            raise ProfileError(f"{zone_id}: type must be one of {sorted(_ZONE_TYPES)}")

        baselines = entry.get("baselines") or {}
        diurnal = entry.get("diurnal") or {}
        for parameter in PARAMETERS:
            if parameter not in baselines:
                raise ProfileError(f"{zone_id}: missing baseline for {parameter}")
            if parameter not in diurnal:
                raise ProfileError(f"{zone_id}: missing diurnal amplitude for {parameter}")
            low, high = RANGES[parameter]
            if not low <= float(baselines[parameter]) <= high:
                raise ProfileError(f"{zone_id}.{parameter}: baseline outside accepted range")

        profiles.append(
            ZoneProfile(
                zone_id=zone_id,
                name=str(entry.get("name", zone_id)),
                zone_type=zone_type,
                device_id=str(entry.get("device_id", f"esp32-{zone_id}")),
                baselines={p: float(baselines[p]) for p in PARAMETERS},
                diurnal={p: float(diurnal[p]) for p in PARAMETERS},
            )
        )

    missing = set(ZONE_IDS) - seen
    if missing:
        raise ProfileError(f"{path}: missing zones {sorted(missing)}")
    return sorted(profiles, key=lambda p: ZONE_IDS.index(p.zone_id))


def _rng(seed: int, zone_id: str, parameter: str, tick: int) -> random.Random:
    key = f"{seed}|{zone_id}|{parameter}|{tick}".encode()
    return random.Random(zlib.crc32(key))


def _drift_sign(seed: int, zone_id: str, parameter: str) -> int:
    key = f"drift|{seed}|{zone_id}|{parameter}".encode()
    return 1 if zlib.crc32(key) % 2 == 0 else -1


def diurnal_shape(when: datetime) -> float:
    """Return 0.0 at 03:00 and 1.0 at 15:00, smoothly in between."""
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    return 0.5 * (1.0 + math.cos(2.0 * math.pi * (hour - 15.0) / 24.0))


def _slow_drift(profile: ZoneProfile, parameter: str, elapsed_s: float, seed: int) -> float:
    hours = max(elapsed_s, 0.0) / 3600.0
    raw = DRIFT_PER_HOUR[parameter] * hours * _drift_sign(seed, profile.zone_id, parameter)
    limit = MAX_DRIFT[parameter]
    return max(-limit, min(limit, raw))


def generate(
    profile: ZoneProfile,
    parameter: str,
    when: datetime,
    elapsed_s: float,
    tick: int,
    seed: int,
) -> float:
    """Generate one deterministic, physically plausible sample."""
    shape = diurnal_shape(when)
    base = profile.baseline(parameter)
    amplitude = profile.amplitude(parameter)
    rng = _rng(seed, profile.zone_id, parameter, tick)

    if parameter == "temperature":
        value = base + amplitude * shape + rng.gauss(0.0, NOISE_SIGMA[parameter])
    elif parameter == "humidity":
        # Ventilation dries the air as the load (temperature) peaks.
        value = base + amplitude * (1.0 - shape) + rng.gauss(0.0, NOISE_SIGMA[parameter])
    elif parameter == "noise":
        # Shift activity is steeper than a sinusoid: use shape**1.6.
        value = base + amplitude * (shape**1.6) + rng.gauss(0.0, NOISE_SIGMA[parameter])
    elif parameter == "air_quality":
        value = (
            base
            + amplitude * (0.25 + 0.75 * shape)
            + 0.8 * (1.0 - shape) * 40.0
            + rng.gauss(0.0, NOISE_SIGMA[parameter])
        )
    elif parameter == "pm25":
        value = base + amplitude * shape + rng.gauss(0.0, NOISE_SIGMA[parameter])
    elif parameter == "pm10":
        # Coarse fraction tracks PM2.5 plus local dust resuspension.
        pm25 = generate(profile, "pm25", when, elapsed_s, tick, seed)
        value = pm25 * 2.05 + 3.0 * shape + rng.gauss(0.0, NOISE_SIGMA[parameter])
    elif parameter == "voltage":
        # Load-dependent sag, smallest at night.
        value = base - amplitude * shape + rng.gauss(0.0, NOISE_SIGMA[parameter])
    else:  # pragma: no cover - guarded by PARAMETERS
        raise ProfileError(f"unknown parameter '{parameter}'")

    value += _slow_drift(profile, parameter, elapsed_s, seed)
    low, high = RANGES[parameter]
    value = max(low, min(high, value))
    return round(value, DECIMALS[parameter])
