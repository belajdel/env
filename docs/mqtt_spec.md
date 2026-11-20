# MQTT Specification

## Overview

The platform uses MQTT 3.1.1 over TLS 1.2 for all sensor communication. The broker is Eclipse Mosquitto 2.0.

---

## Connection Parameters

| Parameter | Value |
|-----------|-------|
| Protocol | MQTT 3.1.1 |
| Transport | TLS 1.2 (port 8883) |
| WebSocket | TLS 1.2 (port 9001) |
| QoS | 1 (At Least Once) |
| Keep Alive | 60 seconds |
| Clean Session | false (persistent session) |
| Client ID | `{device_id}` or `{service}-{hostname}` |
| Username | Per-device/service |
| Password | Per-device/service (from `.env`) |
| Client Cert | Required (mTLS) |
| CA Cert | `infra/certs/ca/ca.crt` |

---

## Topic Structure

### Format
```
factory/{zone_id}/{parameter}
```

### Zone IDs (7 fixed)
| Zone ID | Description |
|---------|-------------|
| prod-01 | Production Line 1 |
| prod-02 | Production Line 2 |
| prod-03 | Production Line 3 |
| store-01 | Storage Area 1 |
| store-02 | Storage Area 2 |
| tech-01 | Technical Room 1 |
| tech-02 | Technical Room 2 |

### Parameters (7 canonical)
| Parameter | Unit | Description |
|-----------|------|-------------|
| temperature | °C | Ambient temperature |
| humidity | % | Relative humidity |
| noise | dB | Sound pressure level |
| air_quality | AQI | Air Quality Index |
| pm25 | µg/m³ | Particulate Matter ≤ 2.5µm |
| pm10 | µg/m³ | Particulate Matter ≤ 10µm |
| voltage | V | Supply voltage |

### Examples
```
factory/prod-01/temperature
factory/prod-01/humidity
factory/store-02/pm25
factory/tech-01/voltage
```

### System Topics (Reserved)
```
$SYS/broker/version          # Broker version (health check)
$SYS/broker/clients/connected # Connected client count
$SYS/broker/messages/received # Message rate
factory/+/+/status           # Device status (online/offline)
factory/+/+/command          # Downlink commands (relay control)
```

---

## Payload Format

### Sensor Data (Uplink)
```json
{
  "zone_id": "prod-01",
  "parameter": "temperature",
  "value": 25.5,
  "unit": "°C",
  "timestamp": "2026-01-15T10:30:00.000Z"
}
```

**Field Requirements**:
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| zone_id | string | Yes | Must match 7 valid zones |
| parameter | string | Yes | Must match 7 canonical params |
| value | number | Yes | Within parameter range |
| unit | string | Yes | Must match canonical unit |
| timestamp | string | Yes | ISO-8601 UTC, ±5min of now |

### Device Status (Uplink)
```json
{
  "device_id": "esp32-prod-01",
  "zone_id": "prod-01",
  "status": "online",
  "firmware_version": "1.0.0",
  "ip_address": "192.168.1.101",
  "signal_strength": -45,
  "uptime_seconds": 3600,
  "timestamp": "2026-01-15T10:30:00.000Z"
}
```

**Status Values**: `online`, `offline`, `error`, `maintenance`

### Relay Command (Downlink)
```json
{
  "command": "relay_control",
  "relay": 1,
  "state": "on",
  "requested_by": "admin@factory.com",
  "reason": "Emergency ventilation",
  "timestamp": "2026-01-15T10:30:00.000Z",
  "nonce": "a1b2c3d4"
}
```

**State Values**: `on`, `off`, `toggle`

### Relay Response (Uplink)
```json
{
  "command": "relay_control",
  "relay": 1,
  "state": "on",
  "success": true,
  "actual_state": "on",
  "timestamp": "2026-01-15T10:30:01.000Z",
  "nonce": "a1b2c3d4"
}
```

---

## QoS and Reliability

### QoS 1 Flow
```
Publisher          Broker          Subscriber
  |                |                |
  |--- PUBLISH ----|                |
  |    (QoS 1)     |                |
  |                |--- PUBLISH --->|
  |                |    (QoS 1)     |
  |                |                |
  |<-- PUBACK -----|                |
  |                |                |
  |                |<-- PUBACK -----|
  |                |                |
```

### Retry Logic (Publisher)
- Max retries: 3
- Backoff: 1s, 2s, 4s (exponential)
- After max retries: Store in ring buffer, retry on reconnect

### Ring Buffer (Firmware)
- Size: 1000 messages
- Persistent: No (RAM only)
- Flush on: Reconnect, 90% full

### Last Will and Testament (LWT)
```json
{
  "device_id": "esp32-prod-01",
  "zone_id": "prod-01",
  "status": "offline",
  "timestamp": "2026-01-15T10:30:00.000Z"
}
```
- Topic: `factory/prod-01/status`
- QoS: 1
- Retain: true

---

## Access Control (ACL)

### Device Clients (ESP32 / Simulator)
| Client | Publish | Subscribe |
|--------|---------|-----------|
| prod-01 | factory/prod-01/# | factory/prod-01/command |
| prod-02 | factory/prod-02/# | factory/prod-02/command |
| ... | ... | ... |

### Service Clients
| Client | Publish | Subscribe |
|--------|---------|-----------|
| backend | factory/+/status, factory/+/command/response | factory/+/+ |
| ai-service | (none) | factory/+/+ |
| dashboard | (none) | factory/+/status (WebSocket) |
| mobile | (none) | factory/+/status (WebSocket) |

### ACL File Format (`acl.conf`)
```
# Devices
user prod-01
topic write factory/prod-01/#
topic read factory/prod-01/command

user prod-02
topic write factory/prod-02/#
topic read factory/prod-02/command

# Backend
user backend
topic read factory/+/+
topic write factory/+/status
topic write factory/+/command/response

# AI Service
user ai-service
topic read factory/+/+

# Dashboard (WebSocket)
user dashboard
topic read factory/+/status
```

---

## Certificate Management

### Certificate Hierarchy
```
CA (infra/certs/ca/)
├── ca.crt        # Root CA certificate
├── ca.key        # Root CA private key (OFFLINE)
│
├── Server (infra/certs/server/)
│   ├── server.crt    # Mosquitto server cert
│   ├── server.key    # Mosquitto server key
│   └── server.csr    # CSR (for reference)
│
└── Client (infra/certs/client/)
    ├── prod-01.crt / prod-01.key
    ├── prod-02.crt / prod-02.key
    ├── prod-03.crt / prod-03.key
    ├── store-01.crt / store-01.key
    ├── store-02.crt / store-02.key
    ├── tech-01.crt / tech-01.key
    ├── tech-02.crt / tech-02.key
    ├── backend.crt / backend.key
    ├── ai-service.crt / ai-service.key
    └── dashboard.crt / dashboard.key
```

### Certificate Generation
```bash
# Run once during setup
cd infra/certs
./generate_certs.sh

# Creates:
# - CA (4096-bit RSA, 10 years)
# - Server cert (SAN: mosquitto, localhost, 1 year)
# - 10 Client certs (CN=client_id, 1 year)
```

### Certificate Rotation
- **Schedule**: Annually (before expiry)
- **Process**: 
  1. Generate new certs with `generate_certs.sh`
  2. Deploy to `infra/certs/`
  3. `docker compose restart mosquitto backend ai_service dashboard mobile`
  4. Update ESP32 devices via OTA (future)

### Verification
```bash
# Verify cert chain
openssl verify -CAfile ca.crt server.crt
openssl verify -CAfile ca.crt client/prod-01.crt

# Check expiry
openssl x509 -in server.crt -noout -dates
```

---

## Message Rate Limits

| Client Type | Max Messages/sec | Burst Allowance |
|-------------|------------------|-----------------|
| ESP32 Device | 1/parameter (7 total) | 10 |
| Simulator | 1/parameter (7 total) | 20 |
| Backend | 100 | 500 |
| AI Service | 50 | 100 |

**Enforcement**: Mosquitto `max_inflight_messages` and `max_queued_messages`

---

## Error Handling

### Invalid Payload
- Broker does NOT validate payload
- Backend subscriber validates and logs
- Invalid messages: logged, counted, discarded
- Metrics: `mqtt_invalid_payload_total` (Prometheus)

### Connection Failure
| Scenario | Behavior |
|----------|----------|
| TLS handshake fail | Log, retry with backoff |
| Auth fail | Log, alert admin, no retry |
| Network timeout | Exponential backoff (1s, 2s, 4s, 8s, max 60s) |
| Broker restart | Auto-reconnect, resume session |

### Message Loss Prevention
- QoS 1 + persistent session = no loss on brief disconnect
- Ring buffer on device = survives extended disconnect
- Backend writes to MongoDB before ACK = durability

---

## Monitoring

### Key Metrics
| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| `mqtt_connected_clients` | $SYS | < 7 devices |
| `mqtt_messages_received_total` | $SYS | < 100/min |
| `mqtt_publish_errors_total` | Backend | > 10/min |
| `mqtt_invalid_payload_total` | Backend | > 5/min |
| `mqtt_device_last_seen_age` | Backend | > 60s |

### Health Check
```bash
# Broker health
mosquitto_sub -h mosquitto -p 8883 \
  --cafile /mosquitto/certs/ca.crt \
  -t '$SYS/broker/version' -C 1 -i healthcheck

# Topic test
mosquitto_pub -h mosquitto -p 8883 \
  --cafile /mosquitto/certs/ca.crt \
  -t 'factory/prod-01/temperature' \
  -m '{"zone_id":"prod-01","parameter":"temperature","value":25.0,"unit":"°C","timestamp":"2026-01-15T10:30:00Z"}'
```

---

## WebSocket Bridge (Dashboard/Mobile)

### Connection
```
wss://mosquitto:9001/mqtt
```

### Protocol
- MQTT over WebSocket (RFC 6455)
- Same auth (username/password)
- Same topics

### Dashboard Usage
```javascript
const client = mqtt.connect('wss://mosquitto:9001/mqtt', {
  username: 'dashboard',
  password: 'dashpass',
  clientId: 'dashboard-' + Math.random().toString(16).substr(2, 8),
  clean: true,
  reconnectPeriod: 5000,
});

client.subscribe('factory/+/status', (err) => {
  if (!err) console.log('Subscribed to device status');
});

client.on('message', (topic, message) => {
  const data = JSON.parse(message.toString());
  // Update UI
});
```

---

## Firmware Implementation Notes (MicroPython)

### Connection
```python
import ssl
import mqtt

ssl_params = {
    'ca_certs': '/certs/ca.crt',
    'certfile': '/certs/client.crt',
    'keyfile': '/certs/client.key',
    'cert_reqs': ssl.CERT_REQUIRED,
    'tls_version': ssl.PROTOCOL_TLS_CLIENT
}

client = mqtt.MQTTClient(
    client_id='esp32-prod-01',
    server='mosquitto',
    port=8883,
    user='prod-01',
    password='prod01pass',
    keepalive=60,
    ssl=True,
    ssl_params=ssl_params
)

client.set_last_will(
    topic='factory/prod-01/status',
    msg=json.dumps({'device_id': 'esp32-prod-01', 'status': 'offline'}),
    qos=1,
    retain=True
)

client.connect()
```

### Publish Loop
```python
def publish_sensor(parameter, value, unit):
    payload = {
        'zone_id': 'prod-01',
        'parameter': parameter,
        'value': round(value, 2),
        'unit': unit,
        'timestamp': utime.localtime()  # Convert to ISO string
    }
    topic = f'factory/prod-01/{parameter}'
    client.publish(topic, json.dumps(payload), qos=1)

# In main loop (every 10s)
for param, (value, unit) in readings.items():
    publish_sensor(param, value, unit)
```

### Command Handler
```python
def on_message(topic, msg):
    if topic.endswith('/command'):
        cmd = json.loads(msg)
        if cmd['command'] == 'relay_control':
            relay = cmd['relay']
            state = cmd['state']
            # Execute relay control
            execute_relay(relay, state)
            # Respond
            response = {
                'command': 'relay_control',
                'relay': relay,
                'state': get_relay_state(relay),
                'success': True,
                'nonce': cmd['nonce']
            }
            client.publish('factory/prod-01/command/response', json.dumps(response), qos=1)

client.set_callback(on_message)
client.subscribe('factory/prod-01/command')
```

---

## Testing

### Unit Tests (Backend)
```python
def test_mqtt_payload_validation():
    valid = {"zone_id": "prod-01", "parameter": "temperature", "value": 25.0, "unit": "°C", "timestamp": "2026-01-15T10:30:00Z"}
    assert validate_payload(valid) is not None
    
    invalid = {"zone_id": "invalid", "parameter": "temperature", "value": 25.0}
    assert validate_payload(invalid) is None
```

### Integration Tests
```bash
# Start stack
docker compose up -d mosquitto mongodb backend

# Test publish/subscribe
mosquitto_pub ... -t 'factory/prod-01/temperature' -m '...'
# Verify in backend logs + MongoDB

# Test QoS 1 persistence
# 1. Publish with device offline
# 2. Bring device online
# 3. Verify message received
```

### Load Test
```bash
# Simulate 7 devices × 7 params × 6/min = 294 msg/min
# Run for 1 hour, verify no loss, latency < 100ms
```

---

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|------------|
| TLS handshake fail | Cert expired/mismatch | Regenerate certs, check CN/SAN |
| Auth fail | Wrong username/password | Check `.env` matches `acl.conf` |
| Messages not received | ACL mismatch | Verify topic permissions in `acl.conf` |
| High latency | Network/broker overload | Check broker CPU/memory, client rate |
| Device shows offline | LWT triggered | Check device power/network, broker logs |

### Debug Commands
```bash
# Broker logs
docker compose logs mosquitto -f

# Subscribe to all topics
mosquitto_sub -h mosquitto -p 8883 --cafile ca.crt -t 'factory/#' -v

# Check client connections
mosquitto_sub -h mosquitto -p 8883 --cafile ca.crt -t '$SYS/broker/clients/connected' -C 1
```