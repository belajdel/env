# Phase 1 — Final Project Structure

**Status:** target structure for Phase 2+. At Phase 1 exit only `docs/` and the root `README.md` exist; no application code is committed yet.
**Rule:** every service owns its dependencies, tests, and Dockerfile. The root owns only orchestration, shared docs, and environment templates.

```text
env-monitoring/
├── AGENTS.md                          # repo-local copy/pointer to the workspace charter
├── README.md                          # quick start, architecture summary, phase status
├── Makefile                           # dev shortcuts: up, down, test, lint, seed, demo-anomaly
├── docker-compose.yml                 # mosquitto, mongo, backend, ai, dashboard, simulator, nginx
├── .env.example                       # placeholders only; real .env is gitignored
├── .gitignore
├── .editorconfig
├── .pre-commit-config.yaml            # ruff + basic hygiene
│
├── docs/
│   ├── README.md                      # documentation index
│   ├── 01-requirements.md
│   ├── 02-architecture.md
│   ├── 03-database-design.md
│   ├── 04-mqtt-spec.md
│   ├── 05-hardware-wiring.md
│   ├── 06-project-structure.md
│   ├── 07-thresholds.md
│   ├── api.md                         # OpenAPI/Swagger usage and examples
│   ├── security.md                    # threat model, JWT/RBAC, MQTT TLS, audit
│   ├── deployment.md                  # Docker Compose, env, backup/restore, cert rotation
│   ├── testing.md                     # unit/integration/latency test strategy
│   ├── user-guide.md                  # roles, dashboard workflows, alert lifecycle
│   ├── pfe-report.md                  # problem, choices, model comparison, results, limits
│   └── diagrams/                      # exported PNG/SVG for the PFE report
│
├── firmware/                          # MicroPython on ESP32
│   ├── README.md                      # flashing, config, pin table, bench checklist
│   ├── boot.py
│   ├── main.py
│   ├── config.example.py              # committed template; config.py is gitignored
│   ├── lib/
│   │   ├── umqtt/simple.py
│   │   └── dht.py
│   ├── core/
│   │   ├── filtering.py               # median/EMA/outlier helpers (pure, CPython-testable)
│   │   ├── buffer.py                  # LittleFS ring buffer + replay cursor
│   │   ├── clock.py                   # NTP sync / skew guard
│   │   └── health.py                  # buffers, RSSI, sensor faults
│   ├── sensors/
│   │   ├── dht22.py
│   │   ├── mq135.py
│   │   ├── pms5003.py
│   │   ├── noise.py
│   │   └── voltage.py
│   ├── actuators/
│   │   ├── relays.py
│   │   ├── leds.py
│   │   └── lcd.py
│   ├── net/
│   │   ├── wifi.py
│   │   ├── mqtt_client.py             # TLS, LWT, reconnect/backoff, QoS 1
│   │   └── topics.py
│   └── tests/                         # CPython tests for pure logic only
│       ├── test_filtering.py
│       ├── test_buffer.py
│       └── test_topics.py
│
├── simulator/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── README.md
│   ├── simulator/
│   │   ├── __init__.py
│   │   ├── main.py                    # CLI: zones, interval, scenario, seed
│   │   ├── config.py
│   │   ├── profiles.py                # daily cycles, zone baselines, noise/drift
│   │   ├── anomalies.py               # injectable anomaly scenarios
│   │   └── publisher.py               # TLS MQTT, same payload contract as firmware
│   ├── config/
│   │   ├── zones.yaml
│   │   └── scenarios.yaml
│   └── tests/
│       ├── test_payload_contract.py
│       ├── test_profiles.py
│       └── test_anomalies.py
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── README.md
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app factory, lifespan, router wiring
│   │   ├── core/
│   │   │   ├── config.py              # pydantic-settings, env only
│   │   │   ├── security.py            # JWT, bcrypt, OAuth2 password flow
│   │   │   ├── logging.py             # structured JSON logs + request IDs
│   │   │   ├── rate_limit.py
│   │   │   └── exceptions.py
│   │   ├── db/
│   │   │   ├── mongo.py               # Motor client, DB dependency
│   │   │   ├── indexes.py             # idempotent index creation
│   │   │   └── seed.py                # admin, 7 zones, devices, default rules
│   │   ├── models/
│   │   │   ├── common.py              # enums, pagination, UTC helpers
│   │   │   ├── user.py
│   │   │   ├── zone.py
│   │   │   ├── device.py
│   │   │   ├── measurement.py
│   │   │   ├── alert_rule.py
│   │   │   ├── alert.py
│   │   │   ├── ai.py
│   │   │   ├── report.py
│   │   │   └── audit.py
│   │   ├── api/
│   │   │   ├── deps.py                # current user, RBAC guards, DB, pagination
│   │   │   ├── router.py              # /api/v1 router composition
│   │   │   └── v1/
│   │   │       ├── auth.py            # login, refresh, logout, me
│   │   │       ├── users.py
│   │   │       ├── zones.py
│   │   │       ├── devices.py
│   │   │       ├── measurements.py
│   │   │       ├── alerts.py          # list, ack, resolve, history
│   │   │       ├── alert_rules.py
│   │   │       ├── ai.py              # proxy to AI + risk/predictions
│   │   │       ├── reports.py
│   │   │       ├── relays.py
│   │   │       ├── audit.py
│   │   │       ├── ws.py              # /ws authenticated stream
│   │   │       └── health.py
│   │   ├── services/
│   │   │   ├── alert_engine.py        # pure thresholds/duration/correlation
│   │   │   ├── alert_service.py       # persistence, dedup, lifecycle
│   │   │   ├── measurement_service.py # ingest, dedup, aggregates
│   │   │   ├── ai_client.py           # httpx client, timeout, degrade
│   │   │   ├── risk_service.py
│   │   │   ├── notification_service.py
│   │   │   ├── report_service.py      # CSV + PDF
│   │   │   ├── relay_service.py       # command issue + ACK tracking
│   │   │   ├── audit_service.py       # append-only + hash chain
│   │   │   └── zone_service.py
│   │   ├── mqtt/
│   │   │   ├── client.py              # paho/asyncio-mqtt, TLS, backoff
│   │   │   ├── handlers.py            # data/status/state/ack routing
│   │   │   └── topics.py              # build/parse/validate topics
│   │   ├── ws/
│   │   │   ├── manager.py             # connection registry, backpressure
│   │   │   └── events.py              # measurement/alert/risk/status events
│   │   └── workers/
│   │       ├── ingestion.py
│   │       ├── scheduler.py           # risk refresh, weekly report, retrain call
│   │       └── offline_monitor.py     # stale device detection
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   ├── test_alert_engine.py
│       │   ├── test_auth.py
│       │   ├── test_rbac.py
│       │   ├── test_mqtt_ingestion.py
│       │   ├── test_validation.py
│       │   └── test_security.py
│       ├── integration/
│       │   ├── test_measurements_api.py
│       │   ├── test_alerts_api.py
│       │   ├── test_relay_flow.py
│       │   ├── test_ws.py
│       │   └── test_critical_latency.py
│       └── fixtures/
│
├── ai_service/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── README.md
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── schemas.py                 # request/response contracts
│   │   ├── core/
│   │   │   ├── logging.py
│   │   │   └── errors.py
│   │   ├── routers/
│   │   │   ├── predict.py             # POST /predict
│   │   │   ├── anomaly.py             # POST /anomaly
│   │   │   ├── risk.py                # GET /risk/{zone_id}
│   │   │   ├── retrain.py             # POST /retrain
│   │   │   └── report.py              # GET /report/weekly
│   │   └── services/
│   │       ├── features.py            # rolling windows, slopes, correlations
│   │       ├── model_registry.py      # versioned artifacts + metadata
│   │       ├── inference.py
│   │       ├── risk.py                # 0–100 explainable score
│   │       ├── training.py
│   │       └── reporting.py
│   ├── data/
│   │   ├── README.md                  # synthetic data contract + real-data swap guide
│   │   ├── generate_dataset.py        # reproducible seed, cycles, drift, labels
│   │   ├── loaders.py
│   │   ├── raw/.gitkeep
│   │   └── processed/.gitkeep
│   ├── training/
│   │   ├── prepare_features.py
│   │   ├── train_isolation_forest.py
│   │   ├── train_autoencoder.py
│   │   ├── train_lstm.py
│   │   ├── evaluate.py
│   │   ├── compare_models.py          # precision/recall/F1 table + selection
│   │   ├── retrain_pipeline.py        # scheduled retraining entrypoint
│   │   ├── artifacts/.gitkeep
│   │   └── notebooks/
│   │       ├── 01_eda.ipynb
│   │       └── 02_model_comparison.ipynb
│   ├── models/                        # runtime artifacts, gitignored
│   ├── reports/                       # weekly PDF/JSON output volume
│   └── tests/
│       ├── test_features.py
│       ├── test_predict.py
│       ├── test_anomaly.py
│       ├── test_risk.py
│       ├── test_retrain.py
│       └── test_report.py
│
├── dashboard/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── README.md
│   ├── app.py                         # Dash app factory + auth wiring
│   ├── server.py                      # gunicorn entrypoint
│   ├── auth.py                        # login/logout, token refresh, role guards
│   ├── pages/
│   │   ├── overview.py
│   │   ├── zone_detail.py
│   │   ├── history.py
│   │   ├── alerts.py
│   │   ├── ai_risk.py
│   │   ├── reports.py
│   │   └── admin.py
│   ├── callbacks/
│   │   ├── overview.py
│   │   ├── filters.py
│   │   ├── alerts.py
│   │   └── relays.py
│   ├── components/
│   │   ├── charts.py                  # Plotly time series/heatmap/correlation
│   │   ├── kpi_cards.py
│   │   ├── alert_banner.py
│   │   └── zone_map.py
│   ├── services/
│   │   ├── api_client.py              # httpx to backend, token handling
│   │   └── ws_client.py               # dash-extensions WebSocket bridge
│   └── assets/
│       ├── styles.css
│       ├── manifest.json              # PWA manifest
│       ├── service-worker.js
│       └── icons/
│
├── mobile/
│   ├── README.md
│   ├── pwa/
│   │   ├── manifest.json              # served/synced by dashboard assets
│   │   ├── service-worker.js
│   │   └── icons/
│   └── push/
│       ├── fcm_admin.py               # Firebase Admin SDK sender
│       ├── telegram_fallback.py
│       └── templates.py
│
├── infra/
│   ├── mosquitto/
│   │   ├── mosquitto.conf
│   │   ├── aclfile
│   │   └── passwd.example
│   ├── mongo/
│   │   └── init/
│   │       ├── 01-collections.js      # time-series + JSON schema validators
│   │       └── 02-indexes.js          # unique/partial/TTL indexes
│   ├── tls/
│   │   └── generate-certs.sh          # local CA, server cert, per-device creds
│   └── nginx/
│       ├── nginx.conf                 # TLS termination, /api, /ws, /
│       └── conf.d/default.conf
│
└── scripts/
    ├── smoke-test.sh                  # compose health + login + seed check
    ├── load-test.py                   # 100 msg/s MQTT/REST load
    ├── inject-anomaly.sh              # simulator scenario trigger
    └── backup-mongo.sh                # mongodump with timestamp
```

## 1. Entrypoints and ownership

| Concern | Entrypoint / owner |
|---|---|
| Backend API | `backend/app/main.py` → `uvicorn app.main:app` |
| MQTT ingestion | `backend/app/mqtt/client.py` started in FastAPI lifespan |
| AI API | `ai_service/app/main.py` → `uvicorn app.main:app` |
| Dashboard | `dashboard/app.py`; Gunicorn imports `server:server` |
| Simulator | `python -m simulator.main` |
| Firmware | `firmware/main.py` after `boot.py` |
| Seed | `python -m app.db.seed` from `backend/` |
| Indexes | `python -m app.db.indexes` from `backend/`, also on startup |
| TLS/certs | `infra/tls/generate-certs.sh` |
| Notifications | `backend/app/services/notification_service.py` + `mobile/push/` |
| Reports | backend PDF/CSV (`report_service.py`) and AI weekly (`ai_service/app/services/reporting.py`) |

## 2. Dependency direction

```text
dashboard/mobile → backend REST/WS → services → models/db
backend mqtt/api → services → models
backend services → ai_service HTTP (never the reverse)
ai_service → model artifacts + feature data (no Mongo, no MQTT)
firmware/simulator → MQTT only
```

- `alert_engine.py` must remain pure: no FastAPI, Mongo, MQTT, or network imports, so it can be unit-tested deterministically.
- Only `backend/app/db` imports Motor. Repositories/services receive a DB handle through dependencies.
- `backend` must never import `sklearn`, `tensorflow`, or `joblib`.
- Dashboard and mobile never receive MQTT credentials or Mongo credentials.
- PWA assets are authored in `mobile/pwa/` and copied into `dashboard/assets/` at build time; do not edit both copies.

## 3. Build and test layout

- Each service has its own `pyproject.toml` and Dockerfile; no shared installable package is required.
- Pin service images to **Python 3.11-slim**. The host Python is 3.14.10, which is too new for some TensorFlow/ML wheels; do not build `ai_service` against the host interpreter.
- `ruff` config lives in each `pyproject.toml` (line length 100, target Python 3.11); root pre-commit runs all services.
- Backend/AI/simulator tests use `pytest`; dashboard is validated by API-level tests plus a smoke test (Dash callbacks are thin).
- Integration tests that need Mongo/Mosquitto are marked `@pytest.mark.integration` and run only with `docker compose`.
- Firmware pure functions are tested on CPython; hardware-in-the-loop remains a documented bench checklist.

## 4. Generated / ignored artifacts

| Path | Rule |
|---|---|
| `.env` | Never commit; only `.env.example` is tracked. |
| `firmware/config.py`, `firmware/certs/*.key` | Device-specific secrets; gitignored. |
| `infra/tls/certs/` | Generated CA/server/device certs; gitignored. |
| `ai_service/models/*.joblib`, `*.keras`, `*.h5` | Generated model artifacts; tracked only by version metadata, not binaries. |
| `ai_service/data/raw/`, `data/processed/`, `reports/` | Runtime/demo data; gitignored except `.gitkeep`. |
| `backend/app/__pycache__`, `.pytest_cache`, `.ruff_cache`, `htmlcov/` | Tool artifacts; gitignored. |
| `output/`, `*.log` | Runtime output; gitignored. |

## 5. Canonical commands

```bash
# Full demo (simulator instead of hardware)
cd env-monitoring
cp .env.example .env
docker compose up --build

# Real hardware instead of simulator
docker compose up -d mosquitto mongodb backend ai_service dashboard nginx

# Quality gates
docker compose exec backend pytest -q
docker compose exec ai_service pytest -q
docker compose exec backend ruff check .
docker compose exec backend ruff format --check .

# Seed (idempotent)
docker compose exec backend python -m app.db.seed

# Anomaly demo
./scripts/inject-anomaly.sh prod-01 overheat
```

Single test:

```bash
docker compose exec backend pytest tests/unit/test_alert_engine.py::test_critical_after_min_duration -q
```

## 6. Phase 1 state

Only `docs/` exists now. Phase 2 creates `firmware/`, `simulator/`, `backend/`, `dashboard/`, `mobile/`, `infra/`, and the root orchestration files in that order. The structure above is the contract; do not silently move a service or introduce a second dashboard framework.
