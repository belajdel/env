# API Reference

## Base URLs

| Environment | Backend API | AI Service | Dashboard | Mobile |
|-------------|-------------|------------|-----------|--------|
| Local | `http://localhost:8000` | `http://localhost:8001` | `http://localhost:8050` | `http://localhost:8080` |
| Docker | `http://backend:8000` | `http://ai-service:8000` | `http://dashboard:8050` | `http://mobile:8080` |

## Authentication

### JWT Token Flow

```bash
# 1. Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin123!"

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800
}

# 2. Use access token
curl -H "Authorization: Bearer <access_token>" \
  http://localhost:8000/zones

# 3. Refresh when expired
curl -X POST http://localhost:8000/auth/refresh \
  -H "Authorization: Bearer <refresh_token>"
```

### Token Expiry
- Access Token: 30 minutes
- Refresh Token: 7 days

### Roles & Permissions

| Endpoint | admin | operator | maintenance | analyst |
|----------|-------|----------|-------------|---------|
| `/auth/*` | ✓ | ✓ | ✓ | ✓ |
| `/zones` (GET) | ✓ | ✓ | ✓ | ✓ |
| `/zones` (POST/PUT/DELETE) | ✓ | ✗ | ✗ | ✗ |
| `/devices` | ✓ | ✓ | ✓ | ✗ |
| `/measurements` | ✓ | ✓ | ✓ | ✓ |
| `/alerts` (GET) | ✓ | ✓ | ✓ | ✓ |
| `/alerts` (ACK/RESOLVE) | ✓ | ✓ | ✓ | ✗ |
| `/alert-rules` | ✓ | ✓ | ✗ | ✗ |
| `/reports` | ✓ | ✓ | ✗ | ✓ |
| `/relay/control` | ✓ | ✗ | ✓ | ✗ |
| `/ai/*` | ✓ | ✓ | ✗ | ✓ |
| `/ws` | ✓ | ✓ | ✓ | ✓ |

---

## Backend API (Port 8000)

### Authentication

#### POST `/auth/login`
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin123!"
```

#### POST `/auth/refresh`
```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Authorization: Bearer <refresh_token>"
```

#### POST `/auth/register` (admin only)
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@factory.com", "username": "operator1", "password": "Pass123!", "role": "operator"}'
```

#### POST `/auth/password-reset`
```bash
curl -X POST http://localhost:8000/auth/password-reset \
  -H "Content-Type: application/json" \
  -d '{"email": "user@factory.com"}'
```

---

### Zones

#### GET `/zones`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/zones
```

#### GET `/zones/{zone_id}`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/zones/prod-01
```

#### POST `/zones` (admin)
```bash
curl -X POST http://localhost:8000/zones \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"zone_id": "prod-04", "name": "Production Line 4", "type": "production"}'
```

#### PUT `/zones/{zone_id}` (admin)
```bash
curl -X PUT http://localhost:8000/zones/prod-01 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"thresholds": {"temperature": {"warning_max": 30}}}'
```

#### DELETE `/zones/{zone_id}` (admin)
```bash
curl -X DELETE http://localhost:8000/zones/prod-04 \
  -H "Authorization: Bearer <token>"
```

---

### Devices

#### GET `/devices`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/devices
```

#### GET `/devices/{device_id}`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/devices/esp32-prod-01
```

#### POST `/devices` (admin)
```bash
curl -X POST http://localhost:8000/devices \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "esp32-prod-04", "zone_id": "prod-04", "name": "New Sensor"}'
```

---

### Measurements

#### GET `/measurements`
```bash
# Required: zone_id, parameter
# Optional: start, end, limit, aggregation
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/measurements?zone_id=prod-01&parameter=temperature&start=2026-01-15T00:00:00Z&end=2026-01-15T23:59:59Z&limit=100"
```

**Query Parameters**:
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| zone_id | string | Yes | Zone ID |
| parameter | string | Yes | Parameter name |
| start | datetime | No | ISO-8601 UTC |
| end | datetime | No | ISO-8601 UTC |
| limit | int | No | Max results (default 1000) |
| aggregation | string | No | `raw`, `1min`, `1hour`, `1day` |

#### GET `/measurements/latest`
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/measurements/latest?zone_id=prod-01"
```

---

### Alerts

#### GET `/alerts`
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/alerts?zone_id=prod-01&status=open&limit=50"
```

**Query Parameters**:
| Param | Type | Description |
|-------|------|-------------|
| zone_id | string | Filter by zone |
| parameter | string | Filter by parameter |
| status | string | `open`, `acknowledged`, `resolved` |
| level | string | `info`, `warning`, `critical`, `predictive` |
| start | datetime | Start date |
| end | datetime | End date |
| limit | int | Max results |

#### POST `/alerts/{alert_id}/acknowledge`
```bash
curl -X POST http://localhost:8000/alerts/alert_id/acknowledge \
  -H "Authorization: Bearer <token>"
```

#### POST `/alerts/{alert_id}/resolve`
```bash
curl -X POST http://localhost:8000/alerts/alert_id/resolve \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"note": "Issue resolved by restarting HVAC"}'
```

---

### Alert Rules

#### GET `/alert-rules`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/alert-rules
```

#### GET `/alert-rules/{rule_id}`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/alert-rules/rule_id
```

#### POST `/alert-rules` (admin/operator)
```bash
curl -X POST http://localhost:8000/alert-rules \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": "prod-01",
    "parameter": "temperature",
    "threshold_warning_max": 28.0,
    "threshold_critical_max": 35.0,
    "min_duration_seconds": 300,
    "level": "warning"
  }'
```

#### PUT `/alert-rules/{rule_id}` (admin/operator)
```bash
curl -X PUT http://localhost:8000/alert-rules/rule_id \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"threshold_critical_max": 38.0, "enabled": true}'
```

#### DELETE `/alert-rules/{rule_id}` (admin)
```bash
curl -X DELETE http://localhost:8000/alert-rules/rule_id \
  -H "Authorization: Bearer <token>"
```

---

### Reports

#### POST `/reports/generate`
```bash
curl -X POST http://localhost:8000/reports/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": "prod-01",
    "report_type": "weekly",
    "format": "pdf",
    "start_date": "2026-01-13T00:00:00Z",
    "end_date": "2026-01-19T23:59:59Z"
  }'
```

**Formats**: `csv`, `pdf`, `json`

#### GET `/reports`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/reports
```

#### GET `/reports/{report_id}/download`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/reports/report_id/download \
  --output report.pdf
```

---

### Relay Control

#### POST `/relay/control` (admin/maintenance)
```bash
curl -X POST http://localhost:8000/relay/control \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": "prod-01",
    "relay": 1,
    "state": "on",
    "reason": "Emergency ventilation"
  }'
```

**State**: `on`, `off`, `toggle`

#### GET `/relay/status`
```bash
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/relay/status?zone_id=prod-01"
```

---

### AI Proxy Endpoints

#### POST `/ai/predict`
```bash
curl -X POST http://localhost:8000/ai/predict \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"zone_id": "prod-01", "horizon_minutes": 60}'
```

#### POST `/ai/anomaly`
```bash
curl -X POST http://localhost:8000/ai/anomaly \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"zone_id": "prod-01", "measurements": {"temperature": 30.0, "humidity": 60.0}}'
```

#### GET `/ai/risk/{zone_id}`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/ai/risk/prod-01
```

#### GET `/ai/report/weekly`
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/ai/report/weekly
```

---

### WebSocket

#### Connect
```javascript
const ws = new WebSocket('ws://localhost:8000/ws?token=<access_token>');

ws.onopen = () => {
  // Subscribe to zones
  ws.send(JSON.stringify({
    type: 'subscribe',
    zones: ['prod-01', 'prod-02']
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg.data);
};
```

#### Message Types (Server → Client)

| Type | Description | Data |
|------|-------------|------|
| `measurement` | New sensor reading | `{zone_id, parameter, value, unit, timestamp}` |
| `alert` | New/updated alert | Alert object |
| `alert_acknowledged` | Alert acknowledged | `{alert_id, acknowledged_by}` |
| `alert_resolved` | Alert resolved | `{alert_id, resolved_by, note}` |
| `device_status` | Device online/offline | `{device_id, zone_id, status}` |
| `risk_score` | Updated risk score | RiskScoreResponse |
| `prediction` | New AI prediction | PredictionResult |
| `relay_state` | Relay changed | `{zone_id, relay, state}` |

#### Message Types (Client → Server)

| Type | Description | Payload |
|------|-------------|---------|
| `subscribe` | Subscribe to zones | `{zones: string[]}` |
| `unsubscribe` | Unsubscribe from zones | `{zones: string[]}` |
| `ping` | Keepalive | `{}` |
| `get_risk` | Request risk score | `{zone_id: string}` |

---

### Health & Monitoring

#### GET `/health`
```bash
curl http://localhost:8000/health
```

#### GET `/metrics` (Prometheus)
```bash
curl http://localhost:8000/metrics
```

---

## AI Service API (Port 8001)

### Health

#### GET `/api/v1/health`
```bash
curl http://localhost:8001/api/v1/health
```

### Predictions

#### POST `/api/v1/predict`
```bash
curl -X POST http://localhost:8001/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"zone_id": "prod-01", "horizon_minutes": 60, "parameters": ["temperature", "humidity"]}'
```

**Response**:
```json
{
  "zone_id": "prod-01",
  "horizon_minutes": 60,
  "predictions": [
    {
      "parameter": "temperature",
      "predicted_value": 28.5,
      "unit": "°C",
      "confidence": 0.85,
      "breach_risk": "high",
      "time_to_breach": "30 min",
      "current_value": 26.0,
      "threshold_warning": 28.0,
      "threshold_critical": 35.0
    }
  ],
  "model_type": "isolation_forest",
  "model_version": "isolation_forest_v20260115_120000"
}
```

### Anomaly Detection

#### POST `/api/v1/anomaly`
```bash
curl -X POST http://localhost:8001/api/v1/anomaly \
  -H "Content-Type: application/json" \
  -d '{"zone_id": "prod-01", "measurements": {"temperature": 40.0, "humidity": 50.0}}'
```

**Response**:
```json
{
  "zone_id": "prod-01",
  "timestamp": "2026-01-15T10:30:00Z",
  "anomalies": [
    {
      "parameter": "temperature",
      "value": 40.0,
      "anomaly_score": 0.95,
      "is_anomaly": true,
      "expected_range": [15.0, 35.0],
      "contribution": 0.9
    }
  ],
  "overall_anomaly_score": 0.95,
  "model_type": "isolation_forest",
  "model_version": "test_v1"
}
```

### Risk Scoring

#### GET `/api/v1/risk/{zone_id}`
```bash
curl http://localhost:8001/api/v1/risk/prod-01
```

**Response**:
```json
{
  "zone_id": "prod-01",
  "score": 75,
  "level": "high",
  "factors": {
    "parameter_anomalies": {"temperature": 0.8},
    "threshold_proximity": {"temperature": 0.6},
    "trend_direction": {"temperature": "increasing"},
    "historical_alert_frequency": 2.0,
    "ai_prediction_confidence": 0.8
  },
  "model_type": "isolation_forest",
  "model_version": "test_v1"
}
```

### Retraining

#### POST `/api/v1/retrain`
```bash
curl -X POST http://localhost:8001/api/v1/retrain \
  -H "Content-Type: application/json" \
  -d '{"model_type": "isolation_forest", "force": true, "data_source": "mixed"}'
```

#### GET `/api/v1/models`
```bash
curl http://localhost:8001/api/v1/models
```

#### POST `/api/v1/models/{model_id}/activate`
```bash
curl -X POST http://localhost:8001/api/v1/models/model_id/activate
```

#### GET `/api/v1/compare`
```bash
curl http://localhost:8001/api/v1/compare
```

### Retraining Scheduler

#### GET `/api/v1/retraining/jobs`
```bash
curl http://localhost:8001/api/v1/retraining/jobs
```

#### POST `/api/v1/retraining/jobs`
```bash
# Interval job (every 6 hours)
curl -X POST "http://localhost:8001/api/v1/retraining/jobs?job_id=retrain_6h&schedule_type=interval&hours=6"

# Cron job (daily at 3:30 AM)
curl -X POST "http://localhost:8001/api/v1/retraining/jobs?job_id=retrain_daily&schedule_type=cron&hour=3&minute=30"
```

#### DELETE `/api/v1/retraining/jobs/{job_id}`
```bash
curl -X DELETE http://localhost:8001/api/v1/retraining/jobs/retrain_6h
```

#### POST `/api/v1/retraining/trigger`
```bash
curl -X POST http://localhost:8001/api/v1/retraining/trigger \
  -H "Content-Type: application/json" \
  -d '{"model_type": "isolation_forest", "zone_id": "prod-01", "force": true}'
```

### Reports

#### GET `/api/v1/report/weekly`
```bash
curl http://localhost:8001/api/v1/report/weekly
```

### Data Management

#### POST `/api/v1/data/generate-synthetic`
```bash
curl -X POST "http://localhost:8001/api/v1/data/generate-synthetic?days=365&sample_rate_minutes=10&anomaly_ratio=0.05"
```

#### POST `/api/v1/data/clear-training`
```bash
curl -X POST "http://localhost:8001/api/v1/data/clear-training?zone_id=prod-01&synthetic_only=true"
```

### History

#### GET `/api/v1/predictions/history`
```bash
curl "http://localhost:8001/api/v1/predictions/history?zone_id=prod-01&limit=100"
```

#### GET `/api/v1/risk/history`
```bash
curl "http://localhost:8001/api/v1/risk/history?zone_id=prod-01&start=2026-01-15T00:00:00Z"
```

---

## Error Responses

### Standard Error Format
```json
{
  "detail": "Error description",
  "error_code": "ERROR_CODE",
  "field": "field_name"  // for validation errors
}
```

### HTTP Status Codes
| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 429 | Rate Limited |
| 500 | Internal Error |
| 503 | Service Unavailable (AI model not ready) |

### Common Error Codes
| Code | Description |
|------|-------------|
| `INVALID_CREDENTIALS` | Wrong username/password |
| `TOKEN_EXPIRED` | Access token expired |
| `TOKEN_INVALID` | Malformed or tampered token |
| `INSUFFICIENT_PERMISSIONS` | Role doesn't allow action |
| `ZONE_NOT_FOUND` | Invalid zone_id |
| `PARAMETER_INVALID` | Invalid parameter name |
| `MODEL_NOT_READY` | No trained model available |
| `INSUFFICIENT_DATA` | Not enough data for prediction |
| `VALIDATION_ERROR` | Request body validation failed |

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/auth/login` | 5 req | 1 minute |
| `/auth/register` | 3 req | 1 hour |
| `/auth/refresh` | 10 req | 1 minute |
| `/measurements` | 100 req | 1 minute |
| `/alerts` | 50 req | 1 minute |
| `/ai/*` | 30 req | 1 minute |
| `/relay/control` | 10 req | 1 minute |

---

## SDK Examples

### Python Client
```python
import httpx
import asyncio

class MonitoringClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.access_token = None
        self.refresh_token = None
        self.username = username
        self.password = password
    
    async def login(self):
        resp = await self.client.post(
            f"{self.base_url}/auth/login",
            data={"username": self.username, "password": self.password}
        )
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
    
    async def _request(self, method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"
        
        resp = await self.client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        
        if resp.status_code == 401 and self.refresh_token:
            await self._refresh()
            headers["Authorization"] = f"Bearer {self.access_token}"
            resp = await self.client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        
        return resp
    
    async def get_measurements(self, zone_id: str, parameter: str, start: str, end: str):
        resp = await self._request("GET", "/measurements", params={
            "zone_id": zone_id,
            "parameter": parameter,
            "start": start,
            "end": end
        })
        return resp.json()
    
    async def get_risk(self, zone_id: str):
        resp = await self._request("GET", f"/ai/risk/{zone_id}")
        return resp.json()
    
    async def control_relay(self, zone_id: str, relay: int, state: str, reason: str):
        resp = await self._request("POST", "/relay/control", json={
            "zone_id": zone_id,
            "relay": relay,
            "state": state,
            "reason": reason
        })
        return resp.json()

# Usage
async def main():
    client = MonitoringClient("http://localhost:8000", "admin", "Admin123!")
    await client.login()
    
    measurements = await client.get_measurements("prod-01", "temperature", "2026-01-15T00:00:00Z", "2026-01-15T23:59:59Z")
    risk = await client.get_risk("prod-01")
    
    print(f"Risk: {risk['score']} ({risk['level']})")

asyncio.run(main())
```

### JavaScript (Mobile PWA)
```javascript
class APIClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
        this.accessToken = localStorage.getItem('access_token');
        this.refreshToken = localStorage.getItem('refresh_token');
    }
    
    async request(method, path, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        
        if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }
        
        let response = await fetch(`${this.baseUrl}${path}`, {
            method,
            headers,
            ...options
        });
        
        if (response.status === 401 && this.refreshToken) {
            await this.refresh();
            headers['Authorization'] = `Bearer ${this.accessToken}`;
            response = await fetch(`${this.baseUrl}${path}`, { method, headers, ...options });
        }
        
        return response;
    }
    
    async login(username, password) {
        const response = await fetch(`${this.baseUrl}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ username, password })
        });
        
        const data = await response.json();
        this.accessToken = data.access_token;
        this.refreshToken = data.refresh_token;
        localStorage.setItem('access_token', this.accessToken);
        localStorage.setItem('refresh_token', this.refreshToken);
        return data;
    }
    
    async getRisk(zoneId) {
        const response = await this.request('GET', `/ai/risk/${zoneId}`);
        return response.json();
    }
    
    async controlRelay(zoneId, relay, state, reason) {
        const response = await this.request('POST', '/relay/control', {
            body: JSON.stringify({ zone_id: zoneId, relay, state, reason })
        });
        return response.json();
    }
}
```