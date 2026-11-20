# Phase 1 — MQTT Specification

**Broker:** Eclipse Mosquitto 2.x
**Protocol:** MQTT 3.1.1 (required for MicroPython `umqtt.simple` compatibility)
**Transport:** TLS 1.2+ on port `8883`; port `1883` is disabled
**Encoding:** UTF-8 JSON, one message per publish, maximum 4 KiB

## 1. Topic namespace

```text
factory/
├── {zone_id}/
│   ├── {parameter}                    # measurements (3 levels)
│   └── {device_id}/
│       ├── status                     # retained online/offline/degraded
│       ├── state                      # retained relay/LED/sensor state
│       ├── cmd                        # backend → device command
│       └── ack                        # device → backend command result
```

Canonical IDs:

- `zone_id`: `prod-01`, `prod-02`, `prod-03`, `store-01`, `store-02`, `tech-01`, `tech-02`
- `device_id`: `esp32-<zone_id>` (for example `esp32-prod-01`); the simulator uses the same device IDs in payloads (its MQTT client ID is prefixed `sim-`). Never run the simulator and a live device for the same zone: they would fight over retained status/state.
- `parameter`: `temperature`, `humidity`, `noise`, `air_quality`, `pm25`, `pm10`, `voltage`

## 2. Topic catalog

| Topic | Publisher | Subscriber | QoS | Retained | Purpose |
|---|---|---|---:|---:|---|
| `factory/{zone_id}/{parameter}` | ESP32 / simulator | Backend | 1 | No | One measurement sample. |
| `factory/{zone_id}/{device_id}/status` | ESP32 / simulator | Backend | 1 | **Yes** | Device presence, firmware, RSSI, buffer depth. |
| `factory/{zone_id}/{device_id}/state` | ESP32 / simulator | Backend | 1 | **Yes** | Relay/LED/LCD/sensor health snapshot. |
| `factory/{zone_id}/{device_id}/cmd` | Backend only | ESP32 / simulator | 1 | No | Relay command. |
| `factory/{zone_id}/{device_id}/ack` | ESP32 / simulator | Backend | 1 | No | Command result. |

**Retained-message rules**

| Message | Retained | Why |
|---|---:|---|
| Measurement | **No** | A retained stale value is dangerous: a dashboard restart would show an old temperature as current. |
| Status | **Yes** | Lets the backend recover last-known online/offline state after restart. |
| State | **Yes** | Lets the dashboard recover last-known relay/sensor state. |
| Command | **No** | A retained command could be replayed on a later reconnect. |
| ACK | **No** | An ACK is only meaningful to the in-flight command. |

To decommission a device, publish an empty retained message to its `status` and `state` topics so the broker clears the retained values.

## 3. Measurement payload

Publish to `factory/{zone_id}/{parameter}`.

```json
{
  "schema_version": 1,
  "zone_id": "prod-01",
  "device_id": "esp32-prod-01",
  "parameter": "temperature",
  "value": 31.4,
  "unit": "°C",
  "timestamp": "2026-11-20T10:15:30.120Z",
  "seq": 18422,
  "quality": "good",
  "source": "sensor"
}
```

| Field | Type | Required | Validation |
|---|---|---:|---|
| `schema_version` | integer | Yes | Must be `1`. |
| `zone_id` | string | Yes | Must equal the topic's `{zone_id}`. |
| `device_id` | string | Yes | Registered in `devices`; must belong to the zone. |
| `parameter` | string enum | Yes | Must equal the topic's `{parameter}`. |
| `value` | number | Yes | Finite; range by parameter (below). |
| `unit` | string enum | Yes | Must match the parameter's canonical unit. |
| `timestamp` | string | Yes | RFC 3339 UTC with milliseconds; device time, not broker time. |
| `seq` | integer | No | Monotonic per device, 0–4294967295. |
| `quality` | string enum | No | `good` (default), `suspect`, `bad`. |
| `source` | string enum | No | `sensor` (default), `simulator`, `backfill`. |

**Canonical units and accepted ranges**

| Parameter | Unit | Normal range accepted | Reject outside |
|---|---|---|---:|
| `temperature` | `°C` | -40 … 125 | -40 … 125 |
| `humidity` | `%` | 0 … 100 | 0 … 100 |
| `noise` | `dB(A)` | 30 … 140 | 30 … 140 |
| `air_quality` | `ppm` (CO₂-equivalent) | 0 … 5000 | 0 … 5000 |
| `pm25` | `µg/m³` | 0 … 1000 | 0 … 1000 |
| `pm10` | `µg/m³` | 0 … 2000 | 0 … 2000 |
| `voltage` | `V AC` | 0 … 300 | 0 … 300 |

A physically impossible value is stored with `quality: "bad"` for traceability, excluded from alerts/aggregates, and counted as a sensor fault. Unknown parameters or topic/payload mismatches are rejected and security-logged.

**Timestamp rules**

- Device must obtain NTP time before publishing; otherwise it buffers and shows `NO TIME` locally.
- Future skew > 120 s: reject and log `clock_skew`.
- Backlog older than 7 days: accept with `quality: "suspect"` (retention/ordering guard).
- Backend records `ingested_at` separately; alert duration uses the device timestamp.

## 4. Device status payload

Publish to `factory/{zone_id}/{device_id}/status`, retained, QoS 1.

```json
{
  "schema_version": 1,
  "zone_id": "prod-01",
  "device_id": "esp32-prod-01",
  "status": "online",
  "reason": "heartbeat",
  "firmware": "1.0.0",
  "ip": "192.168.10.41",
  "rssi": -61,
  "uptime_s": 86400,
  "buffered_samples": 0,
  "timestamp": "2026-11-20T10:15:30Z"
}
```

| Field | Type | Required | Notes |
|---|---|---:|---|
| `status` | enum | Yes | `online`, `offline`, `degraded`. |
| `reason` | enum | Yes | `boot`, `heartbeat`, `shutdown`, `wifi_lost`, `mqtt_lost`, `lwt`, `sensor_fault`. |
| `firmware` | string | No | Semantic version. |
| `ip` | string | No | Last DHCP address. |
| `rssi` | integer | No | dBm (negative). |
| `uptime_s` | integer | No | Seconds since boot. |
| `buffered_samples` | integer | No | Pending samples waiting for replay. |
| `timestamp` | string | Yes | RFC 3339 UTC. |

The LWT payload is the only status message without `timestamp` (see §5); the backend stamps broker receipt time. Publish `online` immediately after connect and every 60 s as a heartbeat. On graceful shutdown, publish `offline / shutdown`, retain it, then disconnect cleanly.

## 5. Last-will message

Configure the will **before** connecting:

- Topic: `factory/{zone_id}/{device_id}/status`
- QoS: `1`
- Retain: `true`
- Payload: static JSON, deliberately **without a timestamp**

```json
{
  "schema_version": 1,
  "zone_id": "prod-01",
  "device_id": "esp32-prod-01",
  "status": "offline",
  "reason": "lwt"
}
```

The LWT payload is fixed at CONNECT time, so a device-generated timestamp would be stale by the time the broker publishes it. The backend uses broker receipt time as `last_seen_at` and marks the device offline. A clean disconnect discards the will, so no false offline event is emitted after a planned shutdown.

## 6. Device state payload

Publish to `factory/{zone_id}/{device_id}/state`, retained, QoS 1, after every relay/LED change and on connect.

```json
{
  "schema_version": 1,
  "zone_id": "prod-01",
  "device_id": "esp32-prod-01",
  "relays": {
    "1": {"state": "off", "mode": "auto"},
    "2": {"state": "on", "mode": "manual"}
  },
  "leds": {"green": true, "orange": false, "red": false},
  "lcd": {"line1": "T:31.4C H:54%", "line2": "AQ:812 PM2.5:22"},
  "sensor_health": {
    "temperature": "ok",
    "humidity": "ok",
    "noise": "ok",
    "air_quality": "ok",
    "pm25": "ok",
    "pm10": "ok",
    "voltage": "ok"
  },
  "timestamp": "2026-11-20T10:15:31Z"
}
```

- `relays.*.state`: `on | off | unknown`.
- `relays.*.mode`: `auto | manual`.
- `sensor_health.*`: `ok | fault | warmup`.
- This topic is a cache for the UI; it is **not** the source of truth for alerting.

## 7. Relay command and ACK

### Command: backend → device

Topic: `factory/{zone_id}/{device_id}/cmd`, QoS 1, not retained.

```json
{
  "schema_version": 1,
  "command_id": "9c2e4a1f-7b3d-4c55-9e0a-2f6d8b1c3a70",
  "action": "relay.set",
  "relay": 2,
  "state": "on",
  "duration_s": 0,
  "requested_by": "665f1a2b3c4d5e6f708192a1",
  "issued_at": "2026-11-20T10:00:00Z",
  "expires_at": "2026-11-20T10:00:30Z",
  "reason": "Operator requested extraction for 30 min"
}
```

| Field | Type | Required | Notes |
|---|---|---:|---|
| `command_id` | UUID string | Yes | Idempotency key; UUIDv4. |
| `action` | enum | Yes | Currently only `relay.set`. |
| `relay` | integer | Yes | `1` or `2`. |
| `state` | enum | Yes | `on` or `off`. |
| `duration_s` | integer | No | `0` = indefinite; `>0` = auto-off timer on device. |
| `requested_by` | string | Yes | User ID; backend also writes `audit_logs`. |
| `issued_at` | string | Yes | RFC 3339 UTC. |
| `expires_at` | string | Yes | Device rejects an expired command. Default TTL 30 s. |
| `reason` | string | No | Human-readable; never contains secrets. |

### ACK: device → backend

Topic: `factory/{zone_id}/{device_id}/ack`, QoS 1, not retained.

```json
{
  "schema_version": 1,
  "command_id": "9c2e4a1f-7b3d-4c55-9e0a-2f6d8b1c3a70",
  "status": "executed",
  "relay": 2,
  "state": "on",
  "executed_at": "2026-11-20T10:00:00.420Z",
  "reason": null
}
```

`status`: `accepted | rejected | executed | failed`.

**Idempotency**

- Device keeps the last 20 `command_id` values in RAM and ACKs duplicates without re-executing.
- Backend retries the same `command_id` at most twice (5 s apart) if no ACK arrives; it never generates a new ID for a retry.
- After `expires_at`, the device responds `rejected` with `reason: "expired"`.
- A reboot clears the in-RAM dedup cache, but `expires_at` prevents replay of old commands.

## 8. QoS, sessions, and reconnect behavior

| Setting | Device | Backend |
|---|---|---|
| MQTT version | 3.1.1 | 3.1.1 |
| Client ID | `esp32-{zone_id}` (stable) | `backend-ingest-1` (stable) |
| Clean session | `true` | `false` |
| Keepalive | 30 s | 60 s |
| QoS for operational messages | 1 | 1 |
| Max in-flight | 4 | 100 |
| Socket timeout | 10 s | 10 s |

- **At-least-once, not exactly-once.** QoS 1 may duplicate a message; the backend deduplicates on `(device_id, seq)` for measurements and on `active + dedup_key` for alerts.
- **Device clean session = true** avoids delivering a stale queued command after a long outage. Command freshness is enforced by `expires_at`.
- **Backend clean session = false** lets the broker queue QoS 1 data while the backend restarts; the backend processes it with original timestamps.
- **Reconnect:** exponential backoff `1, 2, 4, 8, 16, 32, 60 s` with ±20% jitter; reset after 60 s of stable connection. Republish retained status/state on every reconnect.
- **Offline buffer:** ring buffer of 20,000 samples in LittleFS (≈8 h at 7 parameters / 10 s), oldest-first replay at ≤20 msg/s. Drop-oldest only when full, and report `buffered_samples` plus a dropped counter. Never publish a fabricated timestamp.
- **Broker limits:** `persistence true`, `autosave_interval 60`, `max_queued_messages 10000`, `message_size_limit 4096`, per-client connection limits. Queue limits are a safety net, not the primary buffer.

## 9. TLS, authentication, and ACLs

Mosquitto configuration requirements:

```conf
listener 8883
allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/aclfile
cafile   /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile  /mosquitto/certs/server.key
tls_version tlsv1.2
require_certificate false
```

- Devices verify the server certificate against the project CA and the broker hostname.
- Username = device ID; password is unique per device and provisioned out of band.
- Certificates and passwords are generated by `infra/tls/generate-certs.sh` and never committed.
- The dashboard and mobile app have **no MQTT credentials**; they use REST/WebSocket only.

| Principal | Publish | Subscribe |
|---|---|---|
| `backend` | `factory/+/+/cmd` | `factory/#` |
| `esp32-prod-01` | `factory/prod-01/+` (data), `factory/prod-01/esp32-prod-01/status`, `.../state`, `.../ack` | `factory/prod-01/esp32-prod-01/cmd` |
| `simulator` (demo only) | `factory/+/+`, `factory/+/+/status`, `factory/+/+/state`, `factory/+/+/ack` | `factory/+/+/cmd` |

For 50+ devices, generate the ACL file from the seed/device registry; do not hand-edit it.

## 10. Validation and error handling

| Condition | Backend action |
|---|---|
| Invalid JSON / UTF-8 | Drop; increment `mqtt_invalid_payload`; log topic + client ID. |
| Missing required field / bad type | Drop; log validation error without payload secrets. |
| Topic/payload `zone_id`, `device_id`, or `parameter` mismatch | Drop; security-log; increment `mqtt_spoof_attempt`. |
| Unknown parameter or unit | Drop; log. |
| Value outside physical range | Store `quality: "bad"`; mark sensor fault; exclude from alerts. |
| Future timestamp > 120 s | Reject; log `clock_skew`. |
| Timestamp older than 7 days | Accept with `quality: "suspect"`. |
| Duplicate `(device_id, seq)` within 24 h | Drop duplicate; increment `mqtt_duplicate`. |
| Command expired / invalid relay / unknown action | Device ACKs `rejected`; backend marks command failed and audits. |
| Device offline | Backend marks offline on LWT; dashboard shows stale state, never last value as live. |

## 11. Practical test commands

Use environment variables and the project CA; never paste passwords into docs or shell history in production.

```bash
mosquitto_sub -h localhost -p 8883 --cafile infra/tls/certs/ca.crt \
  -u backend -P "$MQTT_BACKEND_PASSWORD" -t 'factory/#' -v -q 1
```

```bash
mosquitto_pub -h localhost -p 8883 --cafile infra/tls/certs/ca.crt \
  -u simulator -P "$MQTT_SIMULATOR_PASSWORD" \
  -t factory/prod-01/temperature -q 1 \
  -m '{"schema_version":1,"zone_id":"prod-01","device_id":"esp32-prod-01","parameter":"temperature","value":31.4,"unit":"°C","timestamp":"2026-11-20T10:15:30.120Z","seq":18422,"quality":"good","source":"simulator"}'
```

Expected: the backend stores the measurement, updates the dashboard within 2 s, and evaluates the temperature rule. Publishing the same `seq` again should increment the duplicate counter and not create a second row.
