"""Anomaly injection: windowing, value transformation and CLI parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from simulator.anomalies import (
    Anomaly,
    AnomalyEngine,
    InjectionError,
    anomalies_from_scenario,
    anomaly_from_injection,
    load_scenarios,
    parse_injection,
)

SCENARIOS_FILE = Path(__file__).resolve().parents[1] / "config" / "scenarios.yaml"


def test_spike_applies_only_inside_its_window():
    engine = AnomalyEngine([Anomaly("prod-01", "temperature", "spike", 10.0, 60.0, 120.0)])
    assert engine.apply("prod-01", "temperature", 25.0, 0.0) == 25.0
    assert engine.apply("prod-01", "temperature", 25.0, 59.9) == 25.0
    assert engine.apply("prod-01", "temperature", 25.0, 60.0) == pytest.approx(35.0)
    assert engine.apply("prod-01", "temperature", 25.0, 179.9) == pytest.approx(35.0)
    assert engine.apply("prod-01", "temperature", 25.0, 180.0) == 25.0


def test_drift_ramps_linearly():
    engine = AnomalyEngine([Anomaly("prod-01", "temperature", "drift", 10.0, 0.0, 100.0)])
    assert engine.apply("prod-01", "temperature", 25.0, 0.0) == pytest.approx(25.0)
    assert engine.apply("prod-01", "temperature", 25.0, 50.0) == pytest.approx(30.0)
    assert engine.apply("prod-01", "temperature", 25.0, 99.9) == pytest.approx(34.99, abs=0.01)


def test_drift_is_clamped_to_the_physical_range():
    engine = AnomalyEngine([Anomaly("prod-01", "temperature", "drift", 500.0, 0.0, 100.0)])
    assert engine.apply("prod-01", "temperature", 25.0, 99.9) == pytest.approx(125.0)


def test_stuck_freezes_the_first_value_and_releases_afterwards():
    engine = AnomalyEngine([Anomaly("store-01", "temperature", "stuck", 0.0, 10.0, 30.0)])
    assert engine.apply("store-01", "temperature", 19.5, 5.0) == 19.5
    frozen = engine.apply("store-01", "temperature", 19.5, 10.0)
    assert frozen == pytest.approx(19.5)
    assert engine.apply("store-01", "temperature", 20.7, 20.0) == pytest.approx(19.5)
    assert engine.is_stuck("store-01", "temperature", 20.0) is True
    engine.expire(40.0)
    assert engine.is_stuck("store-01", "temperature", 40.0) is False
    assert engine.apply("store-01", "temperature", 20.7, 40.0) == pytest.approx(20.7)


def test_dropout_returns_none_and_does_not_affect_other_parameters():
    engine = AnomalyEngine([Anomaly("store-02", "noise", "dropout", 0.0, 0.0, 60.0)])
    assert engine.apply("store-02", "noise", 51.0, 10.0) is None
    assert engine.apply("store-02", "temperature", 20.0, 10.0) == pytest.approx(20.0)
    assert engine.apply("store-02", "noise", 51.0, 60.0) == pytest.approx(51.0)


def test_anomaly_validation_rejects_bad_input():
    with pytest.raises(InjectionError):
        Anomaly("nowhere", "temperature", "spike", 1.0, 0.0, 10.0)
    with pytest.raises(InjectionError):
        Anomaly("prod-01", "pressure", "spike", 1.0, 0.0, 10.0)
    with pytest.raises(InjectionError):
        Anomaly("prod-01", "temperature", "explode", 1.0, 0.0, 10.0)
    with pytest.raises(InjectionError):
        Anomaly("prod-01", "temperature", "spike", 1.0, 0.0, 0.0)


def test_parse_injection_accepts_the_documented_cli_form():
    fields = parse_injection(
        "zone=prod-01 param=temperature type=spike magnitude=12 duration_s=180 after_s=60"
    )
    anomaly = anomaly_from_injection(fields)
    assert anomaly.zone_id == "prod-01"
    assert anomaly.kind == "spike"
    assert anomaly.magnitude == 12.0
    assert anomaly.start_s == 60.0
    assert anomaly.duration_s == 180.0


def test_parse_injection_accepts_commas_and_defaults():
    fields = parse_injection("zone=tech-01,param=voltage,type=drift")
    anomaly = anomaly_from_injection(fields)
    assert anomaly.magnitude == pytest.approx(-30.0)
    assert anomaly.duration_s == 600.0


@pytest.mark.parametrize(
    "text",
    [
        "zone=prod-01 param=temperature",
        "zone=prod-99 param=temperature type=spike",
        "zone=prod-01 param=pressure type=spike",
        "zone=prod-01 param=temperature type=boom",
        "zone=prod-01 param=temperature type=spike magnitude=abc",
        "zone=prod-01 param=temperature type=spike colour=red",
        "garbage",
    ],
)
def test_parse_injection_rejects_bad_input(text):
    with pytest.raises(InjectionError):
        parse_injection(text)


def test_load_scenarios_covers_the_documented_incidents():
    scenarios = load_scenarios(SCENARIOS_FILE)
    assert set(scenarios) == {
        "overheat",
        "dust_event",
        "power_sag",
        "ventilation_failure",
        "sensor_stuck",
        "sensor_dropout",
    }
    assert scenarios["overheat"].zones == ("prod-01",)
    assert {item.parameter for item in scenarios["dust_event"].anomalies} == {"pm25", "pm10"}


def test_scenario_expands_to_selected_zones():
    scenarios = load_scenarios(SCENARIOS_FILE)
    expanded = anomalies_from_scenario(scenarios["overheat"], ["prod-01", "prod-02"])
    assert {anomaly.zone_id for anomaly in expanded} == {"prod-01"}

    fallback = anomalies_from_scenario(scenarios["power_sag"], ["prod-02"])
    assert {anomaly.zone_id for anomaly in fallback} == {"prod-02"}
