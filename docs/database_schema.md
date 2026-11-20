# Database Schema Documentation

## MongoDB Collections Overview

All collections use `_id` as ObjectId unless specified. Time-series collections use `timestamp` as `timeField`.

---

## 1. measurements (Time-Series)

**Purpose**: Raw sensor readings at 10-second intervals

```javascript
{
  _id: ObjectId,
  timestamp: ISODate,           // timeField, UTC
  metadata: {
    zone_id: "prod-01",         // tag
    parameter: "temperature",   // tag
    unit: "°C"                  // tag
  },
  value: 25.5                   // measurement
}
```

**Indexes**:
```javascript
// Automatic time-series index on timestamp
// Compound for queries
{ "metadata.zone_id": 1, "metadata.parameter": 1, "timestamp": -1 }
```

**TTL**: 90 days (auto-expire via `expireAfterSeconds`)

**Shard Key** (future): `metadata.zone_id`

---

## 2. measurements_1min (Time-Series)

**Purpose**: 1-minute aggregated data for dashboards

```javascript
{
  _id: ObjectId,
  timestamp: ISODate,           // timeField, minute boundary
  metadata: {
    zone_id: "prod-01",
    parameter: "temperature",
    unit: "°C"
  },
  value: 25.3,                  // mean
  min: 24.8,
  max: 25.9,
  count: 6                      // samples in minute
}
```

**TTL**: 365 days

---

## 3. users

**Purpose**: Authentication and authorization

```javascript
{
  _id: ObjectId,
  email: "admin@factory.com",   // unique
  username: "admin",
  hashed_password: "$2b$12$...", // bcrypt
  full_name: "Admin User",
  role: "admin",                // admin, operator, maintenance, analyst
  is_active: true,
  is_superuser: false,
  created_at: ISODate,
  updated_at: ISODate,
  last_login: ISODate,
  failed_login_attempts: 0,
  locked_until: ISODate         // optional
}
```

**Indexes**:
```javascript
{ email: 1 }, { unique: true }
{ username: 1 }, { unique: true }
```

---

## 4. zones

**Purpose**: Zone definitions (7 fixed zones)

```javascript
{
  _id: ObjectId,
  zone_id: "prod-01",           // unique, stable ID
  name: "Production Line 1",
  type: "production",           // production, storage, technical
  description: "Main assembly line",
  relays: [1, 2],               // relay numbers
  thresholds: {                 // default thresholds
    temperature: { warning_min: 18, warning_max: 28, critical_min: 15, critical_max: 35 },
    humidity: { warning_min: 30, warning_max: 70, critical_min: 20, critical_max: 85 },
    noise: { warning_max: 80, critical_max: 95 },
    air_quality: { warning_max: 100, critical_max: 150 },
    pm25: { warning_max: 25, critical_max: 50 },
    pm10: { warning_max: 50, critical_max: 100 },
    voltage: { warning_min: 210, warning_max: 240, critical_min: 200, critical_max: 250 }
  },
  coordinates: { x: 100, y: 200 }, // for floor plan
  is_active: true,
  created_at: ISODate,
  updated_at: ISODate
}
```

**Indexes**:
```javascript
{ zone_id: 1 }, { unique: true }
{ type: 1 }
```

**Seed Data** (7 zones):
| zone_id | name | type | relays |
|---------|------|------|--------|
| prod-01 | Production Line 1 | production | [1, 2] |
| prod-02 | Production Line 2 | production | [1, 2] |
| prod-03 | Production Line 3 | production | [1, 2] |
| store-01 | Storage Area 1 | storage | [1, 2] |
| store-02 | Storage Area 2 | storage | [1, 2] |
| tech-01 | Technical Room 1 | technical | [1, 2] |
| tech-02 | Technical Room 2 | technical | [1, 2] |

---

## 5. devices

**Purpose**: ESP32 device registry

```javascript
{
  _id: ObjectId,
  device_id: "esp32-prod-01",   // unique
  zone_id: "prod-01",
  name: "Production Line 1 Sensor",
  type: "esp32-wroom-32",
  firmware_version: "1.0.0",
  mac_address: "AA:BB:CC:DD:EE:FF",
  ip_address: "192.168.1.101",
  mqtt_username: "prod-01",
  mqtt_topic_prefix: "factory/prod-01",
  sensors: ["temperature", "humidity", "noise", "air_quality", "pm25", "pm10", "voltage"],
  relays: [1, 2],
  status: "online",             // online, offline, error
  last_seen: ISODate,
  config: {                     // device-specific config
    sampling_interval: 10,
    thresholds: {}
  },
  created_at: ISODate,
  updated_at: ISODate
}
```

**Indexes**:
```javascript
{ device_id: 1 }, { unique: true }
{ zone_id: 1 }
{ status: 1 }
```

---

## 6. alerts

**Purpose**: Alert instances with lifecycle

```javascript
{
  _id: ObjectId,
  zone_id: "prod-01",
  parameter: "temperature",
  rule_id: ObjectId,            // ref to alert_rules
  level: "critical",            // info, warning, critical, predictive
  message: "Temperature 40.5°C exceeds critical threshold 35°C",
  value: 40.5,
  threshold: 35.0,
  unit: "°C",
  status: "open",               // open, acknowledged, resolved
  acknowledged_by: ObjectId,    // ref to users
  acknowledged_at: ISODate,
  resolved_by: ObjectId,
  resolved_at: ISODate,
  resolution_note: "Cooling system restarted",
  escalation_level: 0,          // 0=initial, 1=first escalation, etc.
  correlation_id: ObjectId,     // for correlated alerts
  ai_predicted: false,          // true if from AI prediction
  ai_confidence: 0.95,
  created_at: ISODate,
  updated_at: ISODate
}
```

**Indexes**:
```javascript
{ zone_id: 1, status: 1, created_at: -1 }
{ parameter: 1 }
{ level: 1 }
{ status: 1 }
{ created_at: -1 }
{ "acknowledged_by": 1 }
```

**TTL**: 365 days (resolved alerts auto-archive)

---

## 7. alert_rules

**Purpose**: Alert threshold configuration per zone/parameter

```javascript
{
  _id: ObjectId,
  zone_id: "prod-01",
  parameter: "temperature",
  name: "High Temperature Warning",
  description: "Alert when temperature exceeds safe operating range",
  threshold_warning_min: 18.0,
  threshold_warning_max: 28.0,
  threshold_critical_min: 15.0,
  threshold_critical_max: 35.0,
  min_duration_seconds: 300,    // must exceed for 5 min
  level: "warning",             // warning, critical
  enabled: true,
  notification_channels: ["websocket", "push", "email"],
  cooldown_seconds: 600,        // prevent spam
  correlation: {                // cross-sensor correlation
    enabled: false,
    parameters: ["humidity"],
    condition: "both_exceed"
  },
  created_by: ObjectId,         // ref to users
  created_at: ISODate,
  updated_at: ISODate
}
```

**Indexes**:
```javascript
{ zone_id: 1, parameter: 1 }, { unique: true }
{ enabled: 1 }
```

---

## 8. ai_predictions

**Purpose**: AI model predictions for threshold breaches

```javascript
{
  _id: ObjectId,
  zone_id: "prod-01",
  parameter: "temperature",
  prediction_type: "threshold_breach", // threshold_breach, anomaly_score, trend, risk_level
  horizon_minutes: 60,
  predicted_value: 36.2,
  confidence: 0.87,
  breach_risk: "critical",      // low, medium, high, critical
  time_to_breach: "45 min",
  current_value: 30.1,
  threshold_warning: 28.0,
  threshold_critical: 35.0,
  model_type: "isolation_forest",
  model_version: "isolation_forest_v20260115_120000",
  actual_value: 35.8,           // filled later for validation
  is_accurate: true,
  created_at: ISODate,
  validated_at: ISODate
}
```

**Indexes**:
```javascript
{ zone_id: 1, created_at: -1 }
{ model_type: 1, created_at: -1 }
{ prediction_type: 1 }
{ breach_risk: 1 }
```

**TTL**: 30 days

---

## 9. ai_models

**Purpose**: Trained model registry

```javascript
{
  _id: ObjectId,
  model_type: "isolation_forest", // isolation_forest, autoencoder, lstm, ensemble
  version: "isolation_forest_v20260115_120000",
  status: "ready",              // training, ready, failed, deprecated
  is_active: true,              // only one active per type/zone/parameter
  zone_id: "global",            // or specific zone
  parameter: "all",             // or specific parameter
  parameters: ["value_temperature", "value_humidity", ...], // feature names
  hyperparameters: {
    n_estimators: 200,
    contamination: 0.05,
    max_samples: "auto"
  },
  metrics: {
    precision: 0.85,
    recall: 0.92,
    f1: 0.88,
    roc_auc: 0.95,
    false_positive_rate: 0.03,
    false_negative_rate: 0.08
  },
  training_samples: 52416,
  data_source: "mixed",         // real, synthetic, mixed
  model_path: "/app/models/isolation_forest_global_all_v20260115_120000/model.joblib",
  scaler_path: "/app/models/isolation_forest_global_all_v20260115_120000/scaler.joblib",
  created_at: ISODate,
  updated_at: ISODate,
  activated_at: ISODate,
  deprecated_at: ISODate
}
```

**Indexes**:
```javascript
{ model_type: 1, zone_id: 1, parameter: 1, version: -1 }
{ is_active: 1 }
{ status: 1 }
{ created_at: -1 }
```

---

## 10. risk_scores

**Purpose**: Dynamic zone risk scores (0-100)

```javascript
{
  _id: ObjectId,
  zone_id: "prod-01",
  score: 75,                    // 0-100
  level: "high",                // low, medium, high, critical
  factors: {
    parameter_anomalies: { "temperature": 0.8, "humidity": 0.2 },
    threshold_proximity: { "temperature": 0.6, "humidity": 0.1 },
    trend_direction: { "temperature": "increasing", "humidity": "stable" },
    historical_alert_frequency: 2.5,
    ai_prediction_confidence: 0.8
  },
  model_type: "isolation_forest",
  model_version: "isolation_forest_v20260115_120000",
  created_at: ISODate
}
```

**Indexes**:
```javascript
{ zone_id: 1, created_at: -1 }
{ level: 1 }
{ score: -1 }
```

**TTL**: 30 days

---

## 11. training_data

**Purpose**: Labeled samples for model training

```javascript
{
  _id: ObjectId,
  zone_id: "prod-01",
  parameter: "temperature",
  features: {
    value_temperature: 25.0,
    value_humidity: 50.0,
    value_pm25: 12.0,
    value_pm10: 25.0,
    value_noise: 55.0,
    value_air_quality: 45.0,
    value_voltage: 230.0,
    temperature_mean_1h: 24.5,
    temperature_std_1h: 0.5,
    temperature_trend_1h: 0.1,
    hour_of_day: 12.0,
    day_of_week: 2.0,
    is_weekend: 0.0,
    hour_sin: 0.0,
    hour_cos: -1.0,
    doy_sin: 0.5,
    doy_cos: 0.866,
    proximity_warning_max: -0.3,
    cross_humidity: 50.0,
    cross_pm25: 12.0,
    cross_pm10: 25.0
  },
  label: 0,                   // 0=normal, 1=anomaly
  timestamp: ISODate,
  is_synthetic: true,
  created_at: ISODate
}
```

**Indexes**:
```javascript
{ zone_id: 1, parameter: 1, timestamp: 1 }
{ label: 1 }
{ is_synthetic: 1 }
{ timestamp: -1 }
```

---

## 12. model_metadata

**Purpose**: Detailed training metadata for reproducibility

```javascript
{
  _id: ObjectId,
  model_type: "isolation_forest",
  version: "isolation_forest_v20260115_120000",
  training_config: {
    zone_id: "global",
    parameter: "all",
    data_source: "mixed",
    train_test_split: 0.8,
    validation_split: 0.1,
    random_state: 42,
    contamination: 0.05
  },
  data_stats: {
    n_samples: 52416,
    n_features: 23,
    anomaly_rate: 0.048,
    zones: 7,
    parameters: 7,
    date_range: { start: "2025-01-15", end: "2026-01-15" }
  },
  metrics: {
    precision: 0.85,
    recall: 0.92,
    f1: 0.88,
    roc_auc: 0.95,
    confusion_matrix: [[48000, 1200], [800, 2416]]
  },
  feature_importance: {
    value_temperature: 0.15,
    value_humidity: 0.12,
    temperature_trend_1h: 0.08,
    hour_sin: 0.07,
    ...
  },
  training_duration_seconds: 45.2,
  created_at: ISODate
}
```

**Indexes**:
```javascript
{ model_type: 1, version: -1 }
{ created_at: -1 }
```

---

## 13. reports

**Purpose**: Generated report metadata

```javascript
{
  _id: ObjectId,
  zone_id: "prod-01",           // or null for all zones
  report_type: "weekly",        // daily, weekly, monthly, custom
  format: "pdf",                // csv, pdf, json
  title: "Weekly Environmental Report - Week 3",
  description: "Summary of zone conditions and alerts",
  date_range: {
    start: ISODate("2026-01-13T00:00:00Z"),
    end: ISODate("2026-01-19T23:59:59Z")
  },
  file_path: "/app/reports/weekly_prod-01_20260119.pdf",
  file_size: 245760,
  generated_by: ObjectId,       // ref to users
  status: "completed",          // pending, generating, completed, failed
  download_count: 5,
  created_at: ISODate,
  completed_at: ISODate
}
```

**Indexes**:
```javascript
{ zone_id: 1, created_at: -1 }
{ report_type: 1 }
{ generated_by: 1 }
```

**TTL**: 365 days

---

## 14. audit_logs

**Purpose**: Security and compliance audit trail

```javascript
{
  _id: ObjectId,
  user_id: ObjectId,            // ref to users (null for system)
  username: "admin",
  action: "relay_control",      // login, logout, relay_on, relay_off, rule_create, etc.
  resource_type: "relay",       // user, zone, device, alert, relay, report
  resource_id: "prod-01:relay:1",
  details: {
    relay: 1,
    state: "on",
    reason: "Emergency ventilation"
  },
  ip_address: "192.168.1.50",
  user_agent: "Mozilla/5.0...",
  success: true,
  error_message: "",
  created_at: ISODate
}
```

**Indexes**:
```javascript
{ user_id: 1, created_at: -1 }
{ action: 1 }
{ resource_type: 1, resource_id: 1 }
{ created_at: -1 }
```

**TTL**: 365 days (compliance retention)

---

## Parameter Reference

### Canonical Parameter IDs (used everywhere)

| Parameter | Unit | Range | Warning Min | Warning Max | Critical Min | Critical Max |
|-----------|------|-------|-------------|-------------|--------------|--------------|
| temperature | °C | -10 to 50 | 18 | 28 | 15 | 35 |
| humidity | % | 0 to 100 | 30 | 70 | 20 | 85 |
| noise | dB | 30 to 120 | - | 80 | - | 95 |
| air_quality | AQI | 0 to 500 | - | 100 | - | 150 |
| pm25 | µg/m³ | 0 to 150 | - | 25 | - | 50 |
| pm10 | µg/m³ | 0 to 200 | - | 50 | - | 100 |
| voltage | V | 200 to 250 | 210 | 240 | 200 | 250 |

### Zone Types and Baselines

| Zone Type | Base Temp | Temp Variance | Base Humidity | Humidity Variance |
|-----------|-----------|---------------|---------------|-------------------|
| production | 24°C | 4°C | 50% | 10% |
| storage | 18°C | 2°C | 40% | 5% |
| technical | 22°C | 2°C | 35% | 5% |

---

## Query Patterns

### Get Recent Measurements (Backend Pattern)
```python
# Always bounded by zone, parameter, and time range
cursor = db.measurements.find({
    "metadata.zone_id": zone_id,
    "metadata.parameter": parameter,
    "timestamp": {"$gte": start, "$lte": end}
}).sort("timestamp", -1).limit(1000)
```

### Get Active Alerts
```python
cursor = db.alerts.find({
    "zone_id": zone_id,
    "status": {"$in": ["open", "acknowledged"]}
}).sort("created_at", -1)
```

### Get Active Model
```python
model = db.ai_models.find_one({
    "model_type": "isolation_forest",
    "zone_id": zone_id,  # or "global"
    "parameter": "all",  # or specific
    "is_active": True,
    "status": "ready"
}, sort=[("activated_at", -1)])
```

### Get Zone Risk History
```python
cursor = db.risk_scores.find({
    "zone_id": zone_id,
    "created_at": {"$gte": week_ago}
}).sort("created_at", 1)
```

---

## Migration Notes

### Initial Setup (run once)
```javascript
// Run init-mongo.js on first startup
// Creates all collections, indexes, TTLs, seed data
```

### Schema Evolution
- Add fields with defaults (never required)
- Use `model_config = ConfigDict(extra="allow")` in Pydantic
- Never remove fields, only deprecate
- Version migrations in `infra/mongodb/migrations/`

---

## Backup Strategy

| Collection | Frequency | Retention |
|------------|-----------|-----------|
| users, zones, devices, alert_rules | Daily | 30 days |
| measurements, measurements_1min | Continuous (replica) | 90 days / 365 days |
| alerts, ai_predictions, risk_scores | Daily | 30 days |
| ai_models, model_metadata, training_data | Daily | 90 days |
| reports, audit_logs | Daily | 365 days |