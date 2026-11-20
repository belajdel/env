# User Guide

## Overview

The Environmental Monitoring Platform provides real-time monitoring of 7 industrial zones with AI-powered anomaly detection, predictive analytics, and automated alerting.

### Key Features
- **Real-time Dashboard**: Live sensor data, zone status, alerts
- **Mobile PWA**: Installable app with offline support and push notifications
- **AI Analytics**: Anomaly detection, threshold predictions, risk scoring
- **Alert Management**: Configurable thresholds, acknowledgment, resolution
- **Relay Control**: Remote actuator control with audit trail
- **Reports**: CSV/PDF/JSON export for compliance

---

## Getting Started

### Access URLs
| Interface | URL | Purpose |
|-----------|-----|---------|
| Dashboard | http://localhost:8050 | Full-featured monitoring |
| Mobile PWA | http://localhost:8080 | Mobile-optimized, installable |
| API Docs | http://localhost:8000/docs | Backend API reference |
| AI API Docs | http://localhost:8001/docs | AI Service API reference |

### Default Credentials
```
Username: admin
Password: Admin123!
```
**Change immediately after first login!**

### Supported Browsers
- Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- Mobile: iOS Safari 14+, Chrome for Android 90+

---

## Dashboard Guide

### Navigation
```
┌─────────────────────────────────────────────────┐
│  Environmental Monitoring Platform    [User] ▼ │
├─────────────┬───────────────────────────────────┤
│  ☰ Menu     │                                   │
│  📊 Overview│   Main Content Area               │
│  🏭 Zones   │                                   │
│  🚨 Alerts  │                                   │
│  📈 Reports │                                   │
│  🤖 AI      │                                   │
│  ⚙️ Settings│                                   │
└─────────────┴───────────────────────────────────┘
```

### 1. Overview Page
- **Zone Cards**: 7 cards showing current temp/humidity, status indicator
- **Real-time Charts**: Bar chart for all 7 parameters, 10s auto-refresh
- **Parameter Selector**: Dropdown to focus on specific parameter
- **Time Range**: Last 1 hour / 6 hours / 24 hours

### 2. Zones Page
- **Zone Grid**: All 7 zones with current readings
- **Zone Detail**: Click zone → gauge charts for all parameters
- **Threshold Indicators**: Green/Yellow/Red bands on gauges
- **Relay Status**: Shows relay 1/2 state (ON/OFF)

### 3. Alerts Page
#### Active Alerts
| Column | Description |
|--------|-------------|
| Zone | Zone ID |
| Parameter | Sensor parameter |
| Level | Info / Warning / Critical / Predictive |
| Message | Alert description |
| Value | Current reading |
| Threshold | Breached threshold |
| Since | Time alert opened |
| Actions | Acknowledge / Resolve |

#### Alert History
- Filter by: Zone, Parameter, Level, Status, Date range
- Pagination: 25/50/100 per page
- Export: CSV/PDF

#### Acknowledging Alerts
1. Click **Acknowledge** on active alert
2. Enter optional note
3. Alert status → `acknowledged`, timestamp recorded

#### Resolving Alerts
1. Click **Resolve** on acknowledged alert
2. Enter resolution note (required)
3. Alert status → `resolved`, timestamp recorded

### 4. Reports Page
#### Generate Report
1. Select **Zone** (or All Zones)
2. Select **Report Type**: Daily / Weekly / Monthly / Custom
3. Select **Format**: CSV / PDF / JSON
4. Set **Date Range** (for custom)
5. Click **Generate**

#### Report History
- List of generated reports with download links
- Status: Pending / Generating / Completed / Failed
- Auto-cleanup after 30 days

### 5. AI Analytics Page
#### Risk Scores
- Circular gauge per zone (0-100)
- Color: Green (0-30), Yellow (30-60), Orange (60-80), Red (80-100)
- Factors: Anomalies, Threshold proximity, Trends, Alert frequency

#### Predictions
- Threshold breach predictions per parameter
- Confidence score (0-1)
- Time to breach estimate
- Risk level: Low / Medium / High / Critical

#### Model Performance
- Comparison table: Isolation Forest vs Autoencoder vs LSTM
- Metrics: Precision, Recall, F1, ROC-AUC
- Best model highlighted

### 6. Settings Page
#### Alert Rules
| Action | Description |
|--------|-------------|
| Add Rule | Configure threshold per zone/parameter |
| Edit Rule | Modify thresholds, duration, notifications |
| Toggle | Enable/disable rule |
| Delete | Remove rule (admin only) |

**Rule Fields**:
- Zone, Parameter
- Warning Min/Max, Critical Min/Max
- Minimum Duration (seconds)
- Alert Level (Warning/Critical)
- Notification Channels (WebSocket, Push, Email)
- Cooldown Period
- Cross-sensor Correlation (optional)

#### Relay Control
- Manual ON/OFF/Toggle per relay
- Reason required (audit log)
- Role-restricted (admin/maintenance only)
- Real-time status updates

---

## Mobile PWA Guide

### Installation
1. Open http://localhost:8080 in mobile browser
2. **Chrome Android**: Menu → "Add to Home Screen"
3. **Safari iOS**: Share → "Add to Home Screen"
4. App icon appears on home screen, works offline

### Navigation
```
┌─────────────────────┐
│  ☰  Monitoring  🔔  │  ← Top bar (menu, notifications)
├─────────────────────┤
│                     │
│                     │
│    Main Content     │  ← Swipe or tap tabs
│                     │
│                     │
├─────────────────────┤
│ 📊 🏭 🚨 📈 🤖 ⚙️  │  ← Bottom navigation (5 tabs)
└─────────────────────┘
```

### Tabs
| Tab | Icon | Content |
|-----|------|---------|
| Dashboard | 📊 | Zone cards, live chart, active alerts |
| Zones | 🏭 | Zone list → detail with gauges |
| Alerts | 🚨 | Active + history, filter, ack/resolve |
| Reports | 📈 | Generate, history, download |
| AI | 🤖 | Risk scores, predictions, model info |

### Features
- **Offline Mode**: Cached data available without network
- **Push Notifications**: Critical alerts via FCM/Telegram
- **Background Sync**: Actions queued when offline
- **Auto-refresh**: 10s when online, manual refresh when offline
- **Responsive**: Works on phone, tablet, desktop

### Gestures
- Pull down → Refresh
- Swipe left/right on zone cards → Navigate zones
- Long press alert → Quick actions (acknowledge/resolve)

---

## Alert Management

### Alert Levels
| Level | Icon | Description | Response Time |
|-------|------|-------------|---------------|
| Info | ℹ️ | Informational, no action needed | N/A |
| Warning | ⚠️ | Approaching threshold | < 1 hour |
| Critical | 🔴 | Threshold exceeded | < 15 minutes |
| Predictive | 🔮 | AI predicts future breach | < 4 hours |

### Alert Lifecycle
```
OPEN → ACKNOWLEDGED → RESOLVED
  ↓           ↓           ↓
Auto        Operator    Operator
created     acknowledges  resolves
            within SLA   with note
```

### SLA Targets
| Level | Acknowledge | Resolve |
|-------|-------------|---------|
| Critical | 5 min | 30 min |
| Warning | 30 min | 4 hours |
| Predictive | 2 hours | 24 hours |
| Info | 24 hours | N/A |

### Escalation
- Unacknowledged critical → Page on-call (Telegram/FCM)
- Unresolved after 2x SLA → Escalate to manager
- All escalations logged in audit trail

---

## Relay Control

### Safety Rules
1. **Authorization Required**: Admin or Maintenance role
2. **Reason Mandatory**: Every action logged with reason
3. **Confirmation**: Toggle requires explicit confirmation
4. **Fail-Safe**: Relays OPEN on MQTT disconnect
5. **Interlock**: Prevent conflicting states (e.g., heater + AC)

### Control Panel
```
Zone: prod-01
┌─────────────┬─────────────┐
│ Relay 1     │ Relay 2     │
│ Ventilation │ Heater      │
│ ● OFF       │ ● OFF       │
│ [ON] [OFF]  │ [ON] [OFF]  │
└─────────────┴─────────────┘
Reason: _________________ [Execute]
```

### Audit Trail
Every relay action recorded:
- Timestamp, User, Zone, Relay, State, Reason
- Viewable in Settings → Audit Logs
- Exportable for compliance

---

## AI Analytics

### Risk Score (0-100)
**Calculation**:
- 40% Parameter anomalies (max across parameters)
- 30% Threshold proximity (max across parameters)
- 15% Trend direction (increasing = higher risk)
- 10% Alert frequency (last 24 hours)
- 5% AI prediction confidence (inverse)

**Levels**:
| Score | Level | Action |
|-------|-------|--------|
| 0-30 | Low | Routine monitoring |
| 30-60 | Medium | Increase sampling, review trends |
| 60-80 | High | Prepare mitigation, check equipment |
| 80-100 | Critical | Immediate intervention |

### Threshold Breach Predictions
- **Horizon**: 5 min to 24 hours
- **Method**: Trend extrapolation + anomaly scoring
- **Output**: Predicted value, confidence, time to breach
- **Use Case**: Proactive maintenance scheduling

### Anomaly Detection
- **Real-time**: POST current readings → anomaly scores
- **Threshold-based**: Critical/Warning zone proximity
- **Statistical**: Isolation Forest on multivariate features
- **Output**: Per-parameter score, overall score, expected range

### Weekly Report
Generated every Monday, includes:
- Zone-by-zone summary
- Prediction accuracy
- Model performance trends
- Actionable recommendations

---

## Reporting

### Report Types
| Type | Description | Frequency |
|------|-------------|-----------|
| Daily | 24-hour summary | Manual/Scheduled |
| Weekly | 7-day analysis + AI report | Every Monday |
| Monthly | 30-day trends + compliance | 1st of month |
| Custom | User-defined range | On-demand |

### Formats
| Format | Use Case |
|--------|----------|
| CSV | Data analysis, Excel import |
| PDF | Compliance, management review |
| JSON | System integration, API |

### Scheduled Reports
1. Settings → Reports → Schedule
2. Select type, format, recipients
3. Set cron expression (e.g., `0 6 * * 1` = Monday 6 AM)
4. Reports auto-generated and emailed

---

## User Management

### Roles
| Role | Permissions |
|------|-------------|
| **Admin** | Full access: users, zones, devices, relays, all settings |
| **Operator** | View all, acknowledge/resolve alerts, generate reports |
| **Maintenance** | View all, relay control, device management |
| **Analyst** | View all, AI analytics, reports, export data |

### User Operations
- **Create User**: Admin only, Settings → Users → Add
- **Reset Password**: Admin or self-service via email
- **Deactivate**: Admin only, preserves audit trail
- **Audit Log**: All user actions tracked

---

## Troubleshooting

### Common Issues

| Symptom | Cause | Resolution |
|---------|-------|------------|
| Zone shows "No Data" | Device offline | Check device power, network, MQTT connection |
| Alerts not appearing | Rule disabled | Check Alert Rules → Enable |
| Push notifications not working | FCM not configured | Add FCM_SERVER_KEY to .env |
| Mobile PWA won't install | Not HTTPS | Use nginx reverse proxy with TLS |
| Relays not responding | MQTT command failed | Check device online, ACL permissions |
| AI predictions missing | Model not trained | Trigger retrain in AI Settings |
| High latency | Network/broker load | Check Mosquitto metrics, scale if needed |

### Self-Service Diagnostics
1. **Dashboard**: Check device status indicators (green=online)
2. **Mobile**: Pull to refresh, check offline banner
3. **API**: `/health` endpoints for each service
4. **MQTT**: Subscribe to `factory/+/status` for device heartbeats

### When to Contact Admin
- Need new user/role
- Add/modify zones or devices
- Configure alert rules
- Schedule reports
- Relay control (if not maintenance role)
- Certificate renewal

---

## Keyboard Shortcuts (Dashboard)

| Shortcut | Action |
|----------|--------|
| `G` `O` | Go to Overview |
| `G` `Z` | Go to Zones |
| `G` `A` | Go to Alerts |
| `G` `R` | Go to Reports |
| `G` `I` | Go to AI Analytics |
| `G` `S` | Go to Settings |
| `/` | Focus search (in tables) |
| `Esc` | Close modal/dropdown |
| `Enter` | Confirm dialog |
| `R` | Refresh current view |

---

## Mobile PWA Shortcuts

| Action | Gesture |
|--------|---------|
| Refresh | Pull down |
| Zone detail | Tap zone card |
| Alert actions | Long press alert |
| Navigate tabs | Tap bottom icons |
| Search | Pull down + type (in lists) |

---

## Glossary

| Term | Definition |
|------|------------|
| **Zone** | Physical area with sensors (7 total) |
| **Parameter** | Measured variable (temp, humidity, etc.) |
| **Threshold** | Limit that triggers alerts |
| **Anomaly** | Reading deviating from normal pattern |
| **Risk Score** | 0-100 composite risk indicator |
| **Prediction** | AI forecast of future threshold breach |
| **Relay** | Controllable actuator (ventilation, heater) |
| **PWA** | Progressive Web App (installable web app) |
| **FCM** | Firebase Cloud Messaging (push notifications) |
| **MQTT** | Message Queuing Telemetry Transport protocol |
| **QoS** | Quality of Service (0, 1, 2) |
| **LWT** | Last Will and Testament (device offline detection) |