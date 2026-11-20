"""Simulator CLI.

Examples
--------
Publish all seven zones every 10 s with per-device credentials::

    python -m simulator.main

Publish two zones and inject a temperature spike after 60 s::

    python -m simulator.main --zones prod-01,tech-01 \
        --inject "zone=prod-01 param=temperature type=spike magnitude=12 after_s=60 duration_s=180"

Run the "overheat" scenario, and stop after 5 ticks::

    python -m simulator.main --scenario overheat --ticks 5

Print deterministic payloads without touching MQTT::

    python -m simulator.main --dry-run --ticks 2 --seed 42
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from .anomalies import (
    AnomalyEngine,
    InjectionError,
    anomalies_from_scenario,
    anomaly_from_injection,
    load_scenarios,
    parse_injection,
)
from .config import ZONE_IDS, Settings, load_settings
from .profiles import PARAMETERS, ZoneProfile, generate, load_zones
from .publisher import SimulatorPublisher, iso_timestamp, measurement_payload

LOGGER = logging.getLogger("simulator")

_RESERVED_LOG_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, matching the backend's structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_KEYS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str) -> None:
    """Configure structured logging to stdout (never ``print`` in services)."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def parse_zones(value: str) -> list[str]:
    """Parse ``--zones`` and validate against the frozen seven zone IDs."""
    zones = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [zone for zone in zones if zone not in ZONE_IDS]
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown zone_id(s): {', '.join(unknown)}")
    if not zones:
        raise argparse.ArgumentTypeError("at least one zone is required")
    return zones


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    """Build the CLI parser; defaults come from ``.env``."""
    parser = argparse.ArgumentParser(
        prog="python -m simulator.main",
        description="Publish deterministic multi-zone measurements over MQTT/TLS.",
    )
    parser.add_argument(
        "--zones",
        type=parse_zones,
        default=list(ZONE_IDS),
        help="comma-separated zone IDs (default: all seven)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=settings.interval_s,
        help=f"seconds between publishing ticks (default: {settings.interval_s:g})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=settings.seed,
        help=f"deterministic random seed (default: {settings.seed})",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=0,
        help="stop after N ticks; 0 means run until interrupted",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        metavar="NAME",
        help="incident scenario from config/scenarios.yaml (repeatable)",
    )
    parser.add_argument(
        "--inject",
        action="append",
        default=[],
        metavar="SPEC",
        help="ad-hoc anomaly: zone=.. param=.. type=.. [magnitude=.. after_s=.. duration_s=..]",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="print available scenarios and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print payloads to stdout without connecting to MQTT",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="log verbosity (default: INFO)",
    )
    return parser


def build_engine(
    settings: Settings,
    selected_zones: Sequence[str],
    scenario_names: Sequence[str],
    injections: Sequence[str],
) -> AnomalyEngine:
    """Expand scenarios and ad-hoc injections into one engine."""
    engine = AnomalyEngine()
    scenarios = load_scenarios(settings.scenarios_file)

    for name in scenario_names:
        if name not in scenarios:
            raise InjectionError(
                f"unknown scenario '{name}' (available: {', '.join(sorted(scenarios))})"
            )
        engine.extend(anomalies_from_scenario(scenarios[name], selected_zones))
        LOGGER.info(
            "scenario armed",
            extra={"scenario": name, "description": scenarios[name].description},
        )

    for text in injections:
        anomaly = anomaly_from_injection(parse_injection(text))
        engine.add(anomaly)
        LOGGER.info("ad-hoc anomaly armed", extra={"anomaly": anomaly.describe()})

    for anomaly in engine.anomalies:
        LOGGER.debug("anomaly detail", extra={"anomaly": anomaly.describe()})
    return engine


def _print_scenarios(settings: Settings) -> None:
    for name, scenario in sorted(load_scenarios(settings.scenarios_file).items()):
        zones = ", ".join(scenario.zones) or "selected zones"
        print(f"{name:20s} zones={zones:22s} {scenario.description}")


def dry_run(
    profiles: Iterable[ZoneProfile],
    engine: AnomalyEngine,
    settings: Settings,
    ticks: int,
    start: datetime | None = None,
) -> int:
    """Emit deterministic payloads without a broker (used by tests and demos)."""
    profiles = list(profiles)
    start = start or datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
    printed = 0
    for tick in range(1, ticks + 1):
        elapsed = (tick - 1) * settings.interval_s
        when = start + timedelta(seconds=elapsed)
        for profile in profiles:
            for parameter in PARAMETERS:
                value = generate(profile, parameter, when, elapsed, tick, settings.seed)
                adjusted = engine.apply(profile.zone_id, parameter, value, elapsed)
                if adjusted is None:
                    continue
                payload = measurement_payload(
                    profile.zone_id,
                    profile.device_id,
                    parameter,
                    adjusted,
                    when,
                    tick,
                )
                print(json.dumps(payload, ensure_ascii=False))
                printed += 1
        engine.expire(elapsed)
    return printed


def _install_signal_handlers(state: dict[str, bool]) -> None:
    def handler(signum: int, frame: object) -> None:
        LOGGER.info("shutdown requested", extra={"signal": signum})
        state["stop"] = True

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def run(
    settings: Settings,
    profiles: Sequence[ZoneProfile],
    engine: AnomalyEngine,
    ticks: int,
) -> int:
    """Publish until interrupted or until ``ticks`` ticks are done."""
    state = {"stop": False}
    _install_signal_handlers(state)
    publisher = SimulatorPublisher(settings, profiles, engine)
    publisher.start()
    LOGGER.info(
        "simulator started",
        extra={
            "zones": [profile.zone_id for profile in profiles],
            "interval_s": settings.interval_s,
            "seed": settings.seed,
            "shared_credentials": settings.shared_credentials,
            "mqtt": f"{settings.mqtt_host}:{settings.mqtt_port}",
        },
    )

    started = time.monotonic()
    tick = 0
    idle_warned = False
    try:
        while not state["stop"] and (ticks == 0 or tick < ticks):
            tick += 1
            target = started + (tick - 1) * settings.interval_s
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            when = datetime.now(timezone.utc)
            try:
                published = publisher.tick(tick, when)
            except Exception:  # keep the simulator alive; log and retry next tick
                LOGGER.exception("tick failed", extra={"tick": tick})
                published = 0

            if published == 0 and not idle_warned:
                LOGGER.warning("no samples published; broker unreachable?")
                idle_warned = True
            elif published:
                idle_warned = False

            LOGGER.info(
                "tick published",
                extra={"tick": tick, "samples": published, "ts": iso_timestamp(when)},
            )
    finally:
        publisher.stop()
        LOGGER.info("simulator stopped", extra={"ticks": tick})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    settings = load_settings()
    parser = build_parser(settings)
    args = parser.parse_args(argv)

    setup_logging(args.log_level)

    if args.list_scenarios:
        _print_scenarios(settings)
        return 0
    if args.interval <= 0:
        parser.error("--interval must be > 0")
    if args.ticks < 0:
        parser.error("--ticks must be >= 0")
    if args.dry_run and args.ticks == 0:
        parser.error("--dry-run requires --ticks > 0")

    try:
        profiles = [p for p in load_zones(settings.zones_file) if p.zone_id in args.zones]
        engine = build_engine(settings, args.zones, args.scenario, args.inject)
    except (InjectionError, OSError, ValueError) as exc:
        LOGGER.error("configuration error", extra={"error": str(exc)})
        return 2

    if args.dry_run:
        printed = dry_run(profiles, engine, settings, args.ticks)
        LOGGER.info("dry run finished", extra={"samples": printed})
        return 0

    try:
        return run(settings, profiles, engine, args.ticks)
    except (FileNotFoundError, RuntimeError) as exc:
        LOGGER.error("startup failed", extra={"error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
