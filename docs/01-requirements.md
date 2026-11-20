# Phase 1 — Requirements Analysis

**Project:** Intelligent Industrial Environmental Monitoring Platform (PFE)
**Status:** Phase 1 baseline, 2026-11-20
**Scope:** Single industrial site, 7 zones, 7 environmental parameters per zone, one ESP32 reference device per zone. The Python simulator replaces hardware for development and demos.

## 1. Assumptions

| # | Assumption |
|---|---|
| A1 | Seven zones: 3 production, 2 storage, 2 technical rooms. IDs are `prod-01`, `prod-02`, `prod-03`, `store-01`, `store-02`, `tech-01`, `tech-02`. |
| A2 | Nominal sampling period is 10 s; 1-minute aggregates are derived for charts and alerts. |
| A3 | Voltage is single-phase 230 V AC nominal. Bench tests use an isolated low-voltage source; mains wiring is never placed on a breadboard. |
| A4 | Raw measurements are retained for 24 months; alerts 5 years; audit logs 2 years; AI predictions 90 days. |
| A5 | One site and one tenant. Multi-site is documented as future work, not implemented. |
| A6 | The PFE deployment uses a self-signed CA for MQTT/HTTPS. Production must use a public/managed CA. |
| A7 | No real AI dataset exists. Phase 3 uses a reproducible synthetic dataset; the loader is designed so real data can replace it. |
| A8 | Dashboard framework is **Plotly Dash** (decision and justification in `02-architecture.md`). |
| A9 | Default admin credentials come from `SEED_ADMIN_PASSWORD`; first login forces a password change. |

## 2. User roles

| Role | Primary use | Permissions |
|---|---|---|
| `admin` | Platform ownership | Full access; user/role management; zone and threshold configuration; retraining; reports; relay control; audit review. |
| `operator` | Control room / shift supervisor | Live and historical views; acknowledge/resolve alerts; relay control; trigger reports; no user or rule administration. |
| `maintenance` | Field technician | Device health/calibration; acknowledge maintenance alerts; relay control; view history; no user administration. |
| `analyst` | Analysis / PFE evaluation | Read-only measurements, alerts, AI predictions/risk, and report export; no relay control or alert resolution. |

## 3. Functional requirements

| ID | Requirement | Priority | Acceptance criteria |
|---|---|---|---|
| FR-01 | **Continuous acquisition.** Each zone reports temperature, humidity, noise, air quality (MQ135), PM2.5, PM10, and voltage every 10 s. | Must | 7 parameters × 7 zones arrive with correct units; locally filtered values carry a `quality` flag; gaps are visible in history. |
| FR-02 | **Edge resilience.** ESP32 buffers measurements in flash during Wi-Fi/MQTT outages and replays them oldest-first after reconnect. | Must | ≥8 h of buffered samples at 10 s cadence; monotonic `seq`; replay rate-limited; no duplicate rows silently created. |
| FR-03 | **Secure MQTT ingest.** Devices publish over TLS 1.2+ with per-device credentials and topic ACLs. | Must | Anonymous and plaintext connections are refused; topic/payload mismatch is rejected and logged. |
| FR-04 | **Sensor simulator.** A Python simulator mimics all 7 zones, daily cycles, noise, drift, and injectable anomalies. | Must | `--zones`, `--interval`, `--scenario`, and `--seed` are supported; runs without hardware; publishes the same payload contract as firmware. |
| FR-05 | **Backend ingestion.** Validate, normalize, deduplicate, timestamp, persist, and forward each measurement. | Must | Bad JSON/out-of-range values do not crash the subscriber; store p95 < 500 ms; counters exposed on `/health`. |
| FR-06 | **Historical queries.** REST API filters measurements by zone, parameter, and date range with pagination. | Must | p95 < 1 s for a 24 h single-parameter query; results are UTC and ordered. |
| FR-07 | **Real-time dashboard.** WebSocket updates for values, alerts, device status, and risk score. | Must | Critical alert appears in the UI < 2 s after threshold duration is met; reconnect shows a clear stale banner. |
| FR-08 | **Historical dashboard.** Time-series charts, multi-zone comparison, correlations, and heatmaps. | Must | Date-range picker, zone/parameter selectors, CSV export; charts remain usable on a 360 px viewport. |
| FR-09 | **Configurable alert rules.** Per zone and parameter: threshold, operator, minimum duration, hysteresis, cooldown, and cross-sensor correlation rules. | Must | Rules are versioned and auditable; changing a threshold takes effect without a restart. |
| FR-10 | **Alert lifecycle.** Alerts move `open → acknowledged → resolved` with actor and timestamps. | Must | History is filterable; duplicate active alerts are suppressed by `dedup_key`; resolution note is preserved. |
| FR-11 | **Notifications.** WebSocket immediate; push via FCM or Telegram fallback. | Must | Delivery attempts and failures are stored per alert; notification outage never blocks the alert itself. |
| FR-12 | **Authentication and RBAC.** JWT access + refresh, OAuth2 password flow, bcrypt, role guards. | Must | Access token expires in 15 min; refresh rotation/revocation works; every non-public route rejects missing/insufficient roles. |
| FR-13 | **Relay control.** Authorized users toggle the two ESP32 relays from the dashboard. | Must | Backend issues a command with `command_id`; device ACKs execution; command and actor are audited; expired commands are rejected. |
| FR-14 | **AI anomaly detection.** Per-zone/parameter anomaly scores from a selected ML model. | Must | Isolation Forest, Autoencoder, and LSTM are compared on precision/recall/F1; the selected model is documented. |
| FR-15 | **Predictive alerts.** Probability of crossing a critical threshold within 15–30 min. | Must | `Predictive` alert includes probability, horizon, model version, and contributing factors. |
| FR-16 | **Dynamic risk score.** Per-zone score 0–100, recomputed at least every 60 s. | Must | Score is explainable by weighted components/drivers and stored historically. |
| FR-17 | **Weekly AI report and recommendations.** Anomalies, patterns, and recommended actions. | Should | Report is retrievable as PDF/JSON; recommendations reference zone/parameter evidence. |
| FR-18 | **Reports.** On-demand PDF and CSV export of measurements, alerts, and AI summaries. | Must | Export respects RBAC and selected filters; PDF includes timestamp, filters, and generator identity. |
| FR-19 | **Audit log.** Sensitive actions (login, user/role change, rule change, relay, report, retrain) are append-only. | Must | Actor, IP, action, resource, outcome, and request ID are recorded; no update/delete API. |
| FR-20 | **Seed and demo.** One command seeds the admin, 7 zones, devices, and default rules. | Must | `docker compose up --build` plus simulator produces a working dashboard and alerts without manual DB edits. |
| FR-21 | **Mobile/PWA.** Responsive, installable UI with alerts and push. | Should | Lighthouse PWA installability checks pass; 360 px layout has no horizontal scroll; push deep-links to the alert. |
| FR-22 | **User administration.** Admin creates/deactivates users, assigns roles and optional zone scopes. | Should | Deactivated users cannot log in; refresh tokens are invalidated on role/password change. |
| FR-23 | **Device health.** Online/offline/degraded status, last-seen, RSSI, buffer depth, sensor faults. | Must | LWT marks a device offline; retained state restores the last known relay/sensor state after backend restart. |

## 4. Non-functional requirements

| ID | Category | Target | Verification |
|---|---|---|---|
| NFR-01 | Latency | Critical alert end-to-end p95 < 2 s, p99 < 3 s (measurement ingress → dashboard). | Timestamped integration test with simulator; latency histogram. |
| NFR-02 | Throughput | 100 msg/s sustained, 500 msg/s for 10 s burst (current load ≈ 5 msg/s). | Locust/k6 or scripted MQTT publisher; no dropped measurements. |
| NFR-03 | AI latency | `/predict` p95 < 500 ms; backend timeout 800 ms. | pytest benchmark and timeout test with AI service stopped. |
| NFR-04 | Availability | 99.5% during the demo window; automatic reconnect after broker/DB restart. | Chaos checks: stop/start Mosquitto, Mongo, AI; dashboard recovers without manual restart. |
| NFR-05 | Durability | At-least-once delivery; ≥8 h outage tolerated at the edge; idempotent alerting. | Buffer replay test; duplicate measurement/alert injection. |
| NFR-06 | Retention | Measurements 24 months; predictions 90 days; alerts 5 years; audit 2 years; reports 12 months. | TTL/index inspection and retention documentation. |
| NFR-07 | Security | TLS 1.2+, bcrypt cost ≥12, JWT 15 min/7 days, auth rate limit 5/min/IP, RBAC on every route, secrets only from env. | Auth/RBAC tests, TLS scan, grep for hardcoded secrets. |
| NFR-08 | Scalability | 50 zones / 350 devices without schema redesign; stateless backend replicas. | Load test; no in-process state required for correctness. |
| NFR-09 | Maintainability | Python 3.11+, type hints, docstrings, ruff, pytest; ≥70% coverage on alert engine, auth, ingestion. | CI/lint/test commands pass locally and in Docker. |
| NFR-10 | Portability | Entire stack starts with one `docker compose up --build`; no host Python install required. | Clean-machine smoke test; documented `.env` only. |
| NFR-11 | Observability | Structured JSON logs, request IDs, `/health` for each service, MQTT ingest counters, alert-latency metric. | Health checks and log inspection. |
| NFR-12 | Usability | First meaningful dashboard view < 2 s after login; mobile 360 px+; color + text alert states (not color-only). | Manual UX checklist and accessibility pass. |
| NFR-13 | Safety | Relay outputs have a configurable fail-safe state and default to de-energized on boot/loss of backend. | Power-cycle and broker-loss test; relay state verified. |

## 5. Out of scope (documented, not implemented)

- SCADA/ERP integration, OPC-UA/Modbus gateways.
- Large-scale production deployment, multi-region or multi-tenant operation.
- Certified safety instrumented system (SIL) or legal metrology.
- Native iOS/Android apps.
- Automatic remediation beyond explicit, authorized relay commands (future work).
- Real sensor calibration laboratory; MQ135 values are indicative, not safety-grade.

## 6. Phase 1 exit criteria

1. This requirements baseline is reviewed and frozen for Phase 2.
2. Architecture, database, MQTT, hardware, folder-structure, and threshold documents are approved.
3. A wiring bench test confirms each sensor can be read and each relay/LED/LCD can be driven.
4. No application code is written before this baseline is accepted.
