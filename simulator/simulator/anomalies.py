"""Injectable anomaly scenarios.

The engine is deliberately pure: it receives a value and a monotonic elapsed
time and returns an adjusted value (or ``None`` when a sample must be dropped).
That makes every anomaly type unit-testable without MQTT or a clock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

import yaml

from .config import ZONE_IDS
from .profiles import PARAMETERS, RANGES

ANOMALY_TYPES: tuple[str, ...] = ("spike", "drift", "stuck", "dropout")

DEFAULT_MAGNITUDE: Mapping[str, float] = {
    "temperature": 10.0,
    "humidity": 20.0,
    "noise": 15.0,
    "air_quality": 900.0,
    "pm25": 100.0,
    "pm10": 200.0,
    "voltage": -30.0,
}


class InjectionError(ValueError):
    """Raised for an invalid anomaly definition or CLI injection string."""


@dataclass
class Anomaly:
    """One time-windowed anomaly for a single zone parameter."""

    zone_id: str
    parameter: str
    kind: str
    magnitude: float
    start_s: float
    duration_s: float
    frozen_value: float | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.zone_id not in ZONE_IDS:
            raise InjectionError(f"unknown zone_id '{self.zone_id}'")
        if self.parameter not in PARAMETERS:
            raise InjectionError(f"unknown parameter '{self.parameter}'")
        if self.kind not in ANOMALY_TYPES:
            raise InjectionError(f"unknown anomaly type '{self.kind}' (use {ANOMALY_TYPES})")
        if not math.isfinite(self.magnitude):
            raise InjectionError("magnitude must be finite")
        if self.start_s < 0:
            raise InjectionError("start_s must be >= 0")
        if self.duration_s <= 0:
            raise InjectionError("duration_s must be > 0")

    def matches(self, zone_id: str, parameter: str) -> bool:
        return self.zone_id == zone_id and self.parameter == parameter

    def is_active(self, elapsed_s: float) -> bool:
        return self.start_s <= elapsed_s < self.start_s + self.duration_s

    def progress(self, elapsed_s: float) -> float:
        if self.duration_s <= 0:
            return 1.0
        return max(0.0, min(1.0, (elapsed_s - self.start_s) / self.duration_s))

    def describe(self) -> str:
        return (
            f"{self.kind} {self.zone_id}/{self.parameter} "
            f"magnitude={self.magnitude} start={self.start_s}s duration={self.duration_s}s"
        )


class AnomalyEngine:
    """Apply all active anomalies to generated samples."""

    def __init__(self, anomalies: Iterable[Anomaly] = ()) -> None:
        self._anomalies: list[Anomaly] = list(anomalies)

    @property
    def anomalies(self) -> tuple[Anomaly, ...]:
        return tuple(self._anomalies)

    def add(self, anomaly: Anomaly) -> None:
        self._anomalies.append(anomaly)

    def extend(self, anomalies: Iterable[Anomaly]) -> None:
        self._anomalies.extend(anomalies)

    def expire(self, elapsed_s: float) -> None:
        """Forget frozen values of finished ``stuck`` windows."""
        for anomaly in self._anomalies:
            if anomaly.kind == "stuck" and not anomaly.is_active(elapsed_s):
                anomaly.frozen_value = None

    def is_stuck(self, zone_id: str, parameter: str, elapsed_s: float) -> bool:
        """True while a ``stuck`` window is active (samples get quality=suspect)."""
        return any(
            anomaly.kind == "stuck"
            and anomaly.matches(zone_id, parameter)
            and anomaly.is_active(elapsed_s)
            for anomaly in self._anomalies
        )

    def apply(
        self,
        zone_id: str,
        parameter: str,
        value: float,
        elapsed_s: float,
    ) -> float | None:
        """Return the adjusted value, or ``None`` when the sample is dropped."""
        result = value
        for anomaly in self._anomalies:
            if not anomaly.matches(zone_id, parameter) or not anomaly.is_active(elapsed_s):
                continue
            if anomaly.kind == "dropout":
                return None
            if anomaly.kind == "spike":
                result += anomaly.magnitude
            elif anomaly.kind == "drift":
                result += anomaly.magnitude * anomaly.progress(elapsed_s)
            elif anomaly.kind == "stuck":
                if anomaly.frozen_value is None:
                    anomaly.frozen_value = result
                result = anomaly.frozen_value
        low, high = RANGES[parameter]
        return max(low, min(high, result))


@dataclass(frozen=True)
class ScenarioAnomaly:
    """An anomaly template from ``scenarios.yaml``."""

    parameter: str
    kind: str
    magnitude: float
    after_s: float
    duration_s: float


@dataclass(frozen=True)
class Scenario:
    """A named, multi-parameter incident."""

    name: str
    description: str
    zones: tuple[str, ...]
    anomalies: tuple[ScenarioAnomaly, ...]


def load_scenarios(path: Path) -> dict[str, Scenario]:
    """Load and validate ``config/scenarios.yaml``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("scenarios")
    if not isinstance(entries, dict) or not entries:
        raise InjectionError(f"{path}: expected a non-empty 'scenarios' mapping")

    scenarios: dict[str, Scenario] = {}
    for name, entry in entries.items():
        anomalies = []
        for item in entry.get("anomalies") or []:
            parameter = str(item.get("parameter", ""))
            kind = str(item.get("type", ""))
            if parameter not in PARAMETERS:
                raise InjectionError(f"scenario '{name}': unknown parameter '{parameter}'")
            if kind not in ANOMALY_TYPES:
                raise InjectionError(f"scenario '{name}': unknown type '{kind}'")
            anomalies.append(
                ScenarioAnomaly(
                    parameter=parameter,
                    kind=kind,
                    magnitude=float(item.get("magnitude", DEFAULT_MAGNITUDE[parameter])),
                    after_s=float(item.get("after_s", 0)),
                    duration_s=float(item.get("duration_s", 600)),
                )
            )
        if not anomalies:
            raise InjectionError(f"scenario '{name}': no anomalies defined")
        zones = tuple(str(z) for z in entry.get("zones") or ())
        for zone in zones:
            if zone not in ZONE_IDS:
                raise InjectionError(f"scenario '{name}': unknown zone '{zone}'")
        scenarios[name] = Scenario(
            name=name,
            description=str(entry.get("description", "")),
            zones=zones,
            anomalies=tuple(anomalies),
        )
    return scenarios


def parse_injection(text: str) -> dict[str, str]:
    """Parse ``zone=prod-01 param=temperature type=spike`` into a dict."""
    allowed = {"zone", "param", "type", "duration_s", "magnitude", "after_s"}
    fields: dict[str, str] = {}
    for token in text.replace(",", " ").split():
        if "=" not in token:
            raise InjectionError(f"expected key=value, got '{token}'")
        key, _, value = token.partition("=")
        key = key.strip()
        if key not in allowed:
            raise InjectionError(f"unknown injection key '{key}' (use {sorted(allowed)})")
        if not value:
            raise InjectionError(f"empty value for '{key}'")
        fields[key] = value.strip()

    for required in ("zone", "param", "type"):
        if required not in fields:
            raise InjectionError(f"injection requires '{required}'")

    zone_id = fields["zone"]
    parameter = fields["param"]
    kind = fields["type"]
    if zone_id not in ZONE_IDS:
        raise InjectionError(f"unknown zone_id '{zone_id}'")
    if parameter not in PARAMETERS:
        raise InjectionError(f"unknown parameter '{parameter}'")
    if kind not in ANOMALY_TYPES:
        raise InjectionError(f"unknown type '{kind}' (use {ANOMALY_TYPES})")

    for numeric in ("duration_s", "magnitude", "after_s"):
        if numeric in fields:
            try:
                float(fields[numeric])
            except ValueError as exc:
                raise InjectionError(f"'{numeric}' must be numeric") from exc
    return fields


def anomaly_from_injection(fields: Mapping[str, str]) -> Anomaly:
    """Turn parsed CLI fields into an :class:`Anomaly`."""
    parameter = fields["param"]
    return Anomaly(
        zone_id=fields["zone"],
        parameter=parameter,
        kind=fields["type"],
        magnitude=float(fields.get("magnitude", DEFAULT_MAGNITUDE[parameter])),
        start_s=float(fields.get("after_s", 0)),
        duration_s=float(fields.get("duration_s", 600)),
    )


def anomalies_from_scenario(
    scenario: Scenario,
    selected_zones: Iterable[str],
) -> list[Anomaly]:
    """Expand a scenario for the selected zones.

    If the scenario pins specific zones that are not selected, the selected
    zones are used instead so ``--scenario`` never silently does nothing.
    """
    selected = list(selected_zones)
    zones = [zone for zone in scenario.zones if zone in selected] or selected
    return [
        Anomaly(
            zone_id=zone,
            parameter=item.parameter,
            kind=item.kind,
            magnitude=item.magnitude,
            start_s=item.after_s,
            duration_s=item.duration_s,
        )
        for zone in zones
        for item in scenario.anomalies
    ]
