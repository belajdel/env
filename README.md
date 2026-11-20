# Intelligent Industrial Environmental Monitoring Platform

PFE project: continuous environmental monitoring and predictive alerting for 7 industrial zones, built Python-first with MicroPython/ESP32 edge devices, MQTT, FastAPI, MongoDB, a separate AI service, and a Plotly Dash dashboard.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 — Foundations | Requirements, architecture, database/MQTT specs, hardware, thresholds | **Complete (documentation)** |
| 2 — Development | Firmware, simulator, backend, dashboard, mobile/PWA | Not started |
| 3 — AI, tests, finalization | Synthetic data, model selection, AI service, tests, Compose, docs | Not started |

No application code exists yet. The Phase 1 deliverables are in [`docs/`](docs/README.md).

## What the platform will do

- Acquire temperature, humidity, noise, air quality, PM2.5, PM10, and voltage every 10 s per zone.
- Transmit securely over MQTT/TLS with QoS 1; buffer ≥8 h at the edge during outages.
- Store timestamped history in MongoDB time-series collections.
- Show live and historical data in a responsive dashboard/PWA.
- Evaluate Info / Warning / Critical alerts with duration, hysteresis, and cross-sensor rules.
- Add anomaly detection, threshold-breach prediction, a 0–100 zone risk score, and Predictive alerts.
- Control ventilation/extraction relays through an audited, role-restricted backend flow.
- Export CSV/PDF reports and send push notifications (FCM or Telegram fallback).

## Documentation

Start with [`docs/README.md`](docs/README.md):

1. [Requirements](docs/01-requirements.md)
2. [Architecture](docs/02-architecture.md)
3. [Database design](docs/03-database-design.md)
4. [MQTT specification](docs/04-mqtt-spec.md)
5. [Hardware and wiring](docs/05-hardware-wiring.md)
6. [Project structure](docs/06-project-structure.md)
7. [Alert thresholds](docs/07-thresholds.md)

## Baseline decisions

- **Edge:** ESP32-WROOM-32, MicroPython, one reference device per zone.
- **Transport:** MQTT 3.1.1 over TLS 8883; REST/HTTPS; WebSocket/WSS.
- **Backend:** FastAPI, Pydantic v2, Motor, paho-mqtt, JWT + RBAC.
- **Data:** MongoDB 7 time-series + metadata; 24-month raw retention.
- **AI:** isolated FastAPI service; threshold alerts run in parallel and never wait for inference.
- **UI:** Plotly Dash (chosen over Streamlit for real-time push, routing, auth, and PWA assets).

## Safety

The voltage channel is for monitoring only, not protection. Mains wiring must use an enclosed, fused, isolated installation; the PFE bench must use a safe low-voltage source. Relay fail-safe states require an explicit hazard review.

## Quick start

Phase 1 only: open the documentation. Phase 2 will add the one-command stack:

```bash
cp .env.example .env
docker compose up --build
```

The simulator will replace hardware by default; real devices can use the same MQTT contract.
