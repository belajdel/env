"""Profile generation must be deterministic, plausible and in-range."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from simulator.config import ZONE_IDS
from simulator.profiles import (
    PARAMETERS,
    RANGES,
    load_zones,
    generate,
)

ZONES_FILE = Path(__file__).resolve().parents[1] / "config" / "zones.yaml"


@pytest.fixture(scope="module")
def profiles():
    return load_zones(ZONES_FILE)


def test_loads_exactly_the_seven_frozen_zones(profiles):
    assert [profile.zone_id for profile in profiles] == list(ZONE_IDS)
    assert all(profile.device_id == f"esp32-{profile.zone_id}" for profile in profiles)


def test_device_id_names_are_unique(profiles):
    device_ids = [profile.device_id for profile in profiles]
    assert len(device_ids) == len(set(device_ids)) == 7


def test_generation_is_deterministic(profiles):
    when = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
    first = {
        (profile.zone_id, parameter): generate(profile, parameter, when, 3600.0, 360, 42)
        for profile in profiles
        for parameter in PARAMETERS
    }
    second = {
        (profile.zone_id, parameter): generate(profile, parameter, when, 3600.0, 360, 42)
        for profile in profiles
        for parameter in PARAMETERS
    }
    assert first == second


def test_different_seeds_change_the_noise(profiles):
    when = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
    profile = profiles[0]
    a = [generate(profile, "temperature", when, 0.0, tick, 42) for tick in range(20)]
    b = [generate(profile, "temperature", when, 0.0, tick, 43) for tick in range(20)]
    assert a != b


@pytest.mark.parametrize("parameter", PARAMETERS)
def test_values_stay_inside_accepted_ranges(profiles, parameter):
    low, high = RANGES[parameter]
    when = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
    for profile in profiles:
        for tick in range(1, 200, 7):
            value = generate(profile, parameter, when, tick * 10.0, tick, 42)
            assert low <= value <= high, f"{profile.zone_id}/{parameter} -> {value}"


def test_temperature_peaks_in_the_afternoon(profiles):
    profile = profiles[0]
    afternoon = generate(
        profile, "temperature", datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc), 0.0, 1, 42
    )
    night = generate(
        profile, "temperature", datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc), 0.0, 1, 42
    )
    assert afternoon > night


def test_humidity_is_inversely_correlated_with_temperature(profiles):
    profile = profiles[0]
    afternoon = generate(
        profile, "humidity", datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc), 0.0, 1, 42
    )
    night = generate(
        profile, "humidity", datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc), 0.0, 1, 42
    )
    assert night > afternoon


def test_pm10_is_coarser_than_pm25(profiles):
    when = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    for profile in profiles:
        pm25 = generate(profile, "pm25", when, 600.0, 60, 42)
        pm10 = generate(profile, "pm10", when, 600.0, 60, 42)
        assert pm10 > pm25


def test_slow_drift_is_bounded(profiles):
    """A week-long run must not drift away from the baseline forever."""
    profile = profiles[0]
    when = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    week = generate(profile, "temperature", when, 7 * 24 * 3600.0, 60, 42)
    assert abs(week - profile.baseline("temperature")) < 8.0
