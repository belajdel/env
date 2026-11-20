# Phase 1 — Default Alert Thresholds

These are **defaults**, seeded per zone and editable by an administrator. Every change is versioned and audited. The alert engine must read rules from the database, never hardcode these numbers.

## 1. How thresholds are evaluated

- **Direction:** high and low excursions are separate rules (`direction: "high"` with `gte`, `direction: "low"` with `lte`). A zone/parameter can have both.
- **Minimum duration:** the condition must remain true continuously for the stated time before an alert opens. This rejects sensor spikes.
- **Evaluation source:** slow parameters use 1-minute aggregates; voltage uses 10 s RMS means; noise warning/critical uses 10 s or 1-min Leq as noted.
- **Hysteresis:** a high alert resolves only when the value falls below `threshold − hysteresis`; a low alert resolves only when it rises above `threshold + hysteresis`. Default resolve delay is 5 minutes after that condition.
- **Cooldown:** 900 s suppresses repeat notifications for the same active alert. Escalation (higher level) always notifies.
- **Dedup key:** `zone_id:parameter:direction:level:source:rule_id` (+ `:correlation_id` for correlations); only one active alert per key.
- **Quality:** readings with `quality: "bad"` do not trigger alerts; they raise a sensor-fault/device-degraded event instead.

Format below: **Info / Warning / Critical**. Durations are **I / W / C**.

## 2. High-excursion thresholds

| Parameter | Unit | Normal range | Info ≥ | Warning ≥ | Critical ≥ | Min duration (I/W/C) | Hysteresis | Basis |
|---|---|---:|---:|---:|---:|---|---|---|
| Temperature | °C | 18–28 | 30 | 35 | 45 | 5 min / 2 min / 30 s | 0.5 / 1 / 1 °C | ASHRAE comfort; industrial process/electronics limits |
| Humidity | %RH | 30–60 | 65 | 75 | 85 | 10 min / 5 min / 1 min | 3 / 5 / 5 % | Condensation, mold, corrosion risk above 85 % |
| Noise | dB(A) | < 75 | 75 | 85 | 95 | 5 min / 1 min / 10 s | 2 / 3 / 3 dB | EU 2003/10/EC action levels (80/85 dB); 95 dB critical |
| Air quality (MQ135) | ppm CO₂-eq | < 800 | 1000 | 1500 | 2000 | 10 min / 5 min / 1 min | 50 / 100 / 100 ppm | Ventilation/CO₂ guidance; MQ135 is indicative, not safety-grade |
| PM2.5 | µg/m³ | < 15 | 35 | 75 | 150 | 15 min / 5 min / 1 min | 5 / 10 / 10 | WHO 24 h guideline 15; industrial dust action levels |
| PM10 | µg/m³ | < 45 | 50 | 150 | 300 | 15 min / 5 min / 1 min | 5 / 10 / 10 | WHO 24 h guideline 45; coarse-dust control |
| Voltage | V AC | 218–242 | 242 | 248 | 264 | 2 min / 30 s / 5 s | 2 V | IEC 60038 230 V nominal; ±5/±8/±15 % bands |

**Notes**

- **Noise critical:** use a 10 s Leq or an impulse peak > 105 dB(A); a single impulse can open a critical alert immediately. Warning is based on 1-min Leq.
- **Air quality:** MQ135 responds to multiple gases and drifts; values are CO₂-equivalent trends after clean-air baseline calibration. Do not present them as certified CO₂ measurements.
- **PM values:** 1-minute averages; do not alert on a single PMS frame.
- **Voltage:** measurement is true RMS over 20 mains cycles. A loss below 180 V for 2 s is also Critical (supply failure), independent of the high/low bands.

## 3. Low-excursion thresholds

| Parameter | Unit | Info ≤ | Warning ≤ | Critical ≤ | Min duration (I/W/C) | Hysteresis | Basis |
|---|---|---:|---:|---:|---|---|---|
| Temperature | °C | 15 | 10 | 5 | 5 min / 2 min / 30 s | 0.5 / 1 / 1 °C | Product/comfort/pipe-freeze risk |
| Humidity | %RH | 30 | 20 | 10 | 10 min / 5 min / 1 min | 3 / 5 / 5 % | ESD risk and material brittleness below 20–30 % |
| Voltage | V AC | 218 | 212 | 196 | 2 min / 30 s / 5 s | 2 V | Undervoltage can stall motors/contactors; < 180 V = loss |

## 4. Derived and predictive levels

| Signal | Condition | Level | Notes |
|---|---|---|---|
| Risk score | 40–59 | Info | Moderate risk; watch trend |
| Risk score | 60–79 | Warning | High risk; investigate drivers |
| Risk score | 80–100 | Critical | Immediate attention |
| Threshold-breach probability | ≥ 0.70 within 30 min | Predictive | Opens a `Predictive` alert with horizon/model/probability |
| Threshold-breach probability | ≥ 0.85 within 15 min | Predictive (high priority) | Escalate in UI/notification; still `level: predictive` |
| Anomaly score | Above model threshold (selected in Phase 3) | Predictive | Anomaly alone does not replace a threshold alert |

**Zone risk formula (v1)**

```text
score = threshold_component (max 35)
      + anomaly_component   (max 30)
      + trend_component     (max 20)
      + air_quality_component (max 15)
```

The components and their top drivers are stored in `risk_scores` for explainability. Example: `30 + 20 + 12 + 10 = 72` → `high`.

## 5. Zone-specific overrides

The baseline profile is production. Seed the following overrides:

| Profile / zones | Temperature high (I/W/C) | Temperature low (I/W/C) | Humidity high (I/W/C) | Noise (I/W/C) | PM2.5 (I/W/C) |
|---|---|---|---|---|---|
| Production (`prod-01..03`) | 30 / 35 / 45 °C | 15 / 10 / 5 °C | 65 / 75 / 85 % | 75 / 85 / 95 dB(A) | 35 / 75 / 150 µg/m³ |
| Storage (`store-01..02`) | 32 / 38 / 45 °C | 5 / 2 / 0 °C | 70 / 80 / 85 % | 70 / 80 / 90 dB(A) | 35 / 75 / 150 µg/m³ |
| Technical (`tech-01..02`) | 27 / 30 / 35 °C | 15 / 10 / 5 °C | 60 / 70 / 80 % | 65 / 75 / 85 dB(A) | 15 / 35 / 75 µg/m³ |

Technical rooms use tighter temperature/humidity limits because of electronics and condensation risk. Voltage, PM10, and air-quality defaults remain the baseline unless the site electrician/process owner changes them.

## 6. Cross-sensor correlation rules

Conditions use structured fields (`parameter`, `operator`, `threshold`), never string evaluation.

| ID | Conditions (all must hold) | Window | Min duration | Level | Interpretation / action |
|---|---|---|---:|---|---|
| `corr-overheat` | temperature ≥ 35 °C AND PM2.5 ≥ 75 µg/m³ | 10 min | 60 s | Critical | Possible machine overheating/bearing failure; inspect cooling and dust extraction. |
| `corr-condensation` | humidity ≥ 75 % AND temperature ≤ 20 °C | 10 min | 5 min | Warning | Condensation on cold surfaces; ventilate/dehumidify, check electronics. |
| `corr-dust-event` | PM10 ≥ 150 AND PM2.5 ≥ 75 µg/m³ | 5 min | 2 min | Warning | Dust-generating process or extraction failure; check filters and PPE. |
| `corr-electrical-stress` | voltage ≥ 248 V AND temperature ≥ 35 °C | 5 min | 1 min | Warning | Electrical/thermal stress; notify maintenance/electrician. |
| `corr-ventilation-failure` | air_quality ≥ 1500 ppm AND humidity ≥ 70 % | 10 min | 2 min | Warning | Stale air + humidity suggests ventilation failure; inspect fans/filters. |
| `corr-motor-degradation` | noise ≥ 85 dB(A) AND temperature ≥ 35 °C | 15 min | 5 min | Warning | Persistent noise + heat; preventive-maintenance flag for the motor. |

## 7. Example rule document (temperature high)

```json
{
  "rule_id": "rule-prod-01-temperature-high",
  "name": "Production temperature — high",
  "zone_id": "prod-01",
  "parameter": "temperature",
  "direction": "high",
  "enabled": true,
  "levels": {
    "info":     {"operator": "gte", "threshold": 30, "min_duration_s": 300, "hysteresis": 0.5},
    "warning":  {"operator": "gte", "threshold": 35, "min_duration_s": 120, "hysteresis": 1.0},
    "critical": {"operator": "gte", "threshold": 45, "min_duration_s": 30,  "hysteresis": 1.0}
  },
  "predictive": {"enabled": true, "horizon_min": 30, "probability_threshold": 0.70},
  "correlations": [
    {
      "correlation_id": "corr-overheat",
      "name": "Possible machine overheating",
      "logic": "all",
      "window_s": 600,
      "min_duration_s": 60,
      "level": "critical",
      "conditions": [
        {"parameter": "temperature", "operator": "gte", "threshold": 35},
        {"parameter": "pm25", "operator": "gte", "threshold": 75}
      ],
      "message": "Temperature and PM2.5 are rising together; inspect the machine and ventilation."
    }
  ],
  "notification_channels": ["websocket", "push"],
  "cooldown_s": 900,
  "version": 1
}
```

## 8. Automatic recommendations

These are generated as text suggestions, never as automatic relay actions (future work).

| Condition | Recommendation |
|---|---|
| Temperature warning/critical | Inspect cooling, airflow, and nearby machinery; reduce load; verify ventilation relay. |
| Temperature + PM2.5 correlated | Suspect machine overheating or bearing wear; schedule preventive maintenance and check extraction. |
| Humidity high | Increase ventilation/dehumidification; inspect for leaks and condensation on electrical cabinets. |
| Humidity low | Check ESD controls and material handling; humidify if the process requires it. |
| Noise warning/critical | Enforce hearing protection; inspect bearings/fans; schedule acoustic maintenance. |
| Air quality high | Increase fresh-air intake; check CO₂/VOC sources and filter condition. |
| PM2.5/PM10 high | Check dust extraction, filters, and housekeeping; require PPE where applicable. |
| Voltage deviation | Notify the electrician; check load switching, loose terminals, and upstream supply. |
| Predictive breach | Plan a maintenance/inspection window before the predicted threshold crossing; do not wait for the critical alert. |

## 9. Validation rules for administrators

1. For high rules: `info < warning < critical`; for low rules: `info > warning > critical`.
2. `critical` minimum duration must be ≤ `warning` ≤ `info` (critical reacts fastest).
3. Hysteresis must be > 0 and smaller than the gap to the next level.
4. A rule cannot be enabled without a notification path; `in_app`/WebSocket is always implicit.
5. Changes are rejected if they would leave a zone without a voltage-critical rule.
6. Every update increments `version` and writes `before`/`after` to `audit_logs`.
