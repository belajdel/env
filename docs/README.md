# Documentation Index

Phase 1 (foundations) is documentation-only. No application code exists yet.

| Document | Contents |
|---|---|
| [01-requirements.md](01-requirements.md) | Functional/non-functional requirements, roles, assumptions, scope. |
| [02-architecture.md](02-architecture.md) | Seven-layer Mermaid diagram, measurement sequence, latency budget, failure modes, deployment. |
| [03-database-design.md](03-database-design.md) | JSON schema for all 10 collections, time-series setup, indexes, retention, seed plan. |
| [04-mqtt-spec.md](04-mqtt-spec.md) | Topics, payloads, QoS, retained messages, LWT, commands/ACKs, ACLs, reconnect rules. |
| [05-hardware-wiring.md](05-hardware-wiring.md) | ESP32 pin table, power, voltage levels, sensor warm-up, filtering, bench checklist. |
| [06-project-structure.md](06-project-structure.md) | Final folder tree, entrypoints, ownership, dependency direction, commands. |
| [07-thresholds.md](07-thresholds.md) | Default Info/Warning/Critical thresholds, durations, hysteresis, correlations, recommendations. |

## Frozen baseline decisions

- **7 zones:** `prod-01..03`, `store-01..02`, `tech-01..02`.
- **7 parameters:** temperature, humidity, noise, air quality (MQ135), PM2.5, PM10, voltage.
- **Sampling:** 10 s device cadence; 1-minute aggregates for slow alerts/charts.
- **Dashboard:** Plotly Dash (real-time WebSocket + multi-page + auth fit).
- **Messaging:** MQTT 3.1.1 over TLS 8883, QoS 1, per-device ACLs.
- **Database:** MongoDB 7 time-series for measurements, normal collections for metadata.
- **AI:** separate FastAPI service; threshold alerts never wait for inference.
- **Retention:** measurements 24 months, predictions 90 days, risk 180 days, reports 12 months, audit 2 years.

## Phase gate

Phase 2 may start only after the requirements baseline and these documents are accepted, and the hardware bench checklist in `05-hardware-wiring.md` passes.
