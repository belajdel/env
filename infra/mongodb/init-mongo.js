// MongoDB Initialization Script for Industrial Environmental Monitoring
// Creates time-series collections, indexes, TTLs, and seed data
// Run automatically on container startup via docker-entrypoint-initdb.d

const dbName = 'env_monitoring';
db = db.getSiblingDB(dbName);

// ============================================
// 1. TIME-SERIES COLLECTION: measurements
// ============================================
// Time-series collection for sensor measurements
// timeField: timestamp (ISODate)
// metaField: metadata (zone_id, parameter, device_id)
// granularity: seconds (10s sampling, 1-min aggregates)
try {
    db.createCollection('measurements', {
        timeseries: {
            timeField: 'timestamp',
            metaField: 'metadata',
            granularity: 'seconds'
        },
        expireAfterSeconds: 2592000, // 30 days TTL for raw measurements
        // 1-minute aggregates kept longer (handled by separate collection or aggregation)
    });
    print('Created time-series collection: measurements');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection measurements already exists');
    } else {
        throw e;
    }
}

// Indexes for measurements
db.measurements.createIndex(
    { 'metadata.zone_id': 1, 'metadata.parameter': 1, timestamp: 1 },
    { name: 'idx_zone_param_time', background: true }
);
db.measurements.createIndex(
    { 'metadata.device_id': 1, timestamp: 1 },
    { name: 'idx_device_time', background: true }
);
print('Created indexes on measurements');

// ============================================
// 2. COLLECTION: measurements_1min (1-minute aggregates)
// ============================================
try {
    db.createCollection('measurements_1min', {
        timeseries: {
            timeField: 'timestamp',
            metaField: 'metadata',
            granularity: 'minutes'
        },
        expireAfterSeconds: 31536000, // 1 year TTL for aggregates
    });
    print('Created time-series collection: measurements_1min');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection measurements_1min already exists');
    } else {
        throw e;
    }
}

db.measurements_1min.createIndex(
    { 'metadata.zone_id': 1, 'metadata.parameter': 1, timestamp: 1 },
    { name: 'idx_zone_param_time_1min', background: true }
);
print('Created indexes on measurements_1min');

// ============================================
// 3. COLLECTION: users
// ============================================
try {
    db.createCollection('users');
    print('Created collection: users');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection users already exists');
    } else {
        throw e;
    }
}

db.users.createIndex({ username: 1 }, { unique: true, name: 'idx_username_unique' });
db.users.createIndex({ email: 1 }, { unique: true, name: 'idx_email_unique' });
db.users.createIndex({ role: 1 }, { name: 'idx_role' });
print('Created indexes on users');

// ============================================
// 4. COLLECTION: zones
// ============================================
try {
    db.createCollection('zones');
    print('Created collection: zones');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection zones already exists');
    } else {
        throw e;
    }
}

db.zones.createIndex({ zone_id: 1 }, { unique: true, name: 'idx_zone_id_unique' });
db.zones.createIndex({ type: 1 }, { name: 'idx_type' });
print('Created indexes on zones');

// ============================================
// 5. COLLECTION: devices
// ============================================
try {
    db.createCollection('devices');
    print('Created collection: devices');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection devices already exists');
    } else {
        throw e;
    }
}

db.devices.createIndex({ device_id: 1 }, { unique: true, name: 'idx_device_id_unique' });
db.devices.createIndex({ zone_id: 1 }, { name: 'idx_zone_id' });
db.devices.createIndex({ status: 1 }, { name: 'idx_status' });
print('Created indexes on devices');

// ============================================
// 6. COLLECTION: alert_rules
// ============================================
try {
    db.createCollection('alert_rules');
    print('Created collection: alert_rules');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection alert_rules already exists');
    } else {
        throw e;
    }
}

db.alert_rules.createIndex(
    { zone_id: 1, parameter: 1 },
    { unique: true, name: 'idx_zone_param_unique' }
);
db.alert_rules.createIndex({ enabled: 1 }, { name: 'idx_enabled' });
print('Created indexes on alert_rules');

// ============================================
// 7. COLLECTION: alerts
// ============================================
try {
    db.createCollection('alerts');
    print('Created collection: alerts');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection alerts already exists');
    } else {
        throw e;
    }
}

db.alerts.createIndex({ zone_id: 1, parameter: 1, status: 1, timestamp: -1 }, { name: 'idx_zone_param_status_time' });
db.alerts.createIndex({ status: 1, level: 1, timestamp: -1 }, { name: 'idx_status_level_time' });
db.alerts.createIndex({ acknowledged_by: 1 }, { name: 'idx_acknowledged_by' });
db.alerts.createIndex({ resolved_by: 1 }, { name: 'idx_resolved_by' });
// TTL for resolved alerts: 90 days
db.alerts.createIndex(
    { resolved_at: 1 },
    { expireAfterSeconds: 7776000, name: 'idx_resolved_ttl' }
);
print('Created indexes on alerts');

// ============================================
// 8. COLLECTION: ai_predictions
// ============================================
try {
    db.createCollection('ai_predictions', {
        timeseries: {
            timeField: 'timestamp',
            metaField: 'metadata',
            granularity: 'minutes'
        },
        expireAfterSeconds: 604800, // 7 days TTL
    });
    print('Created time-series collection: ai_predictions');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection ai_predictions already exists');
    } else {
        throw e;
    }
}

db.ai_predictions.createIndex(
    { 'metadata.zone_id': 1, 'metadata.prediction_type': 1, timestamp: 1 },
    { name: 'idx_zone_type_time', background: true }
);
print('Created indexes on ai_predictions');

// ============================================
// 9. COLLECTION: risk_scores
// ============================================
try {
    db.createCollection('risk_scores', {
        timeseries: {
            timeField: 'timestamp',
            metaField: 'metadata',
            granularity: 'minutes'
        },
        expireAfterSeconds: 2592000, // 30 days TTL
    });
    print('Created time-series collection: risk_scores');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection risk_scores already exists');
    } else {
        throw e;
    }
}

db.risk_scores.createIndex(
    { 'metadata.zone_id': 1, timestamp: 1 },
    { name: 'idx_zone_time', background: true }
);
print('Created indexes on risk_scores');

// ============================================
// 10. COLLECTION: reports
// ============================================
try {
    db.createCollection('reports');
    print('Created collection: reports');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection reports already exists');
    } else {
        throw e;
    }
}

db.reports.createIndex({ zone_id: 1, report_type: 1, generated_at: -1 }, { name: 'idx_zone_type_time' });
db.reports.createIndex({ generated_by: 1 }, { name: 'idx_generated_by' });
// TTL: 1 year
db.reports.createIndex(
    { generated_at: 1 },
    { expireAfterSeconds: 31536000, name: 'idx_reports_ttl' }
);
print('Created indexes on reports');

// ============================================
// 11. COLLECTION: audit_logs (append-only with hash chain)
// ============================================
try {
    db.createCollection('audit_logs');
    print('Created collection: audit_logs');
} catch (e) {
    if (e.codeName === 'NamespaceExists') {
        print('Collection audit_logs already exists');
    } else {
        throw e;
    }
}

db.audit_logs.createIndex({ timestamp: 1 }, { name: 'idx_timestamp' });
db.audit_logs.createIndex({ actor_id: 1, timestamp: -1 }, { name: 'idx_actor_time' });
db.audit_logs.createIndex({ action: 1 }, { name: 'idx_action' });
db.audit_logs.createIndex({ resource_type: 1, resource_id: 1 }, { name: 'idx_resource' });
// No TTL - audit logs are permanent
print('Created indexes on audit_logs');

// ============================================
// SEED DATA
// ============================================

// Helper: hash for audit log chain
function hashLog(prevHash, doc) {
    const str = prevHash + JSON.stringify(doc);
    return SHA256(str);
}

// Seed: 7 Zones
const zones = [
    { zone_id: 'prod-01', name: 'Production Line 1', type: 'production', location: 'Building A, Floor 1', description: 'Main production line', created_at: new Date(), updated_at: new Date() },
    { zone_id: 'prod-02', name: 'Production Line 2', type: 'production', location: 'Building A, Floor 1', description: 'Secondary production line', created_at: new Date(), updated_at: new Date() },
    { zone_id: 'prod-03', name: 'Production Line 3', type: 'production', location: 'Building A, Floor 2', description: 'Tertiary production line', created_at: new Date(), updated_at: new Date() },
    { zone_id: 'store-01', name: 'Storage Area 1', type: 'storage', location: 'Building B, Floor 1', description: 'Raw material storage', created_at: new Date(), updated_at: new Date() },
    { zone_id: 'store-02', name: 'Storage Area 2', type: 'storage', location: 'Building B, Floor 1', description: 'Finished goods storage', created_at: new Date(), updated_at: new Date() },
    { zone_id: 'tech-01', name: 'Technical Room 1', type: 'technical', location: 'Building C, Floor 1', description: 'HVAC and electrical room', created_at: new Date(), updated_at: new Date() },
    { zone_id: 'tech-02', name: 'Technical Room 2', type: 'technical', location: 'Building C, Floor 2', description: 'Server and network room', created_at: new Date(), updated_at: new Date() },
];

zones.forEach(zone => {
    db.zones.updateOne(
        { zone_id: zone.zone_id },
        { $setOnInsert: zone },
        { upsert: true }
    );
});
print('Seeded 7 zones');

// Seed: Default Admin User (password: Admin123! - change in production)
// bcrypt hash for "Admin123!" with cost 12
const adminHash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj/RK.PZvO.S';
db.users.updateOne(
    { username: 'admin' },
    {
        $setOnInsert: {
            username: 'admin',
            email: 'admin@envmonitoring.local',
            password_hash: adminHash,
            full_name: 'System Administrator',
            role: 'admin',
            is_active: true,
            created_at: new Date(),
            updated_at: new Date(),
            last_login: null
        }
    },
    { upsert: true }
);
print('Seeded default admin user (password: Admin123!)');

// Seed: Devices (one per zone)
const devices = [
    { device_id: 'prod-01', zone_id: 'prod-01', device_type: 'ESP32-WROOM-32', firmware_version: '1.0.0', status: 'offline', last_seen: null, created_at: new Date(), updated_at: new Date() },
    { device_id: 'prod-02', zone_id: 'prod-02', device_type: 'ESP32-WROOM-32', firmware_version: '1.0.0', status: 'offline', last_seen: null, created_at: new Date(), updated_at: new Date() },
    { device_id: 'prod-03', zone_id: 'prod-03', device_type: 'ESP32-WROOM-32', firmware_version: '1.0.0', status: 'offline', last_seen: null, created_at: new Date(), updated_at: new Date() },
    { device_id: 'store-01', zone_id: 'store-01', device_type: 'ESP32-WROOM-32', firmware_version: '1.0.0', status: 'offline', last_seen: null, created_at: new Date(), updated_at: new Date() },
    { device_id: 'store-02', zone_id: 'store-02', device_type: 'ESP32-WROOM-32', firmware_version: '1.0.0', status: 'offline', last_seen: null, created_at: new Date(), updated_at: new Date() },
    { device_id: 'tech-01', zone_id: 'tech-01', device_type: 'ESP32-WROOM-32', firmware_version: '1.0.0', status: 'offline', last_seen: null, created_at: new Date(), updated_at: new Date() },
    { device_id: 'tech-02', zone_id: 'tech-02', device_type: 'ESP32-WROOM-32', firmware_version: '1.0.0', status: 'offline', last_seen: null, created_at: new Date(), updated_at: new Date() },
];

devices.forEach(device => {
    db.devices.updateOne(
        { device_id: device.device_id },
        { $setOnInsert: device },
        { upsert: true }
    );
});
print('Seeded 7 devices');

// Seed: Default Alert Rules (thresholds from Phase 1)
// Format: { zone_id, parameter, warning_min, warning_max, critical_min, critical_max, min_duration_sec, correlation_rules, enabled }
const alertRules = [
    // Temperature: 18-28°C warning, 15-35°C critical
    { zone_id: 'prod-01', parameter: 'temperature', warning_min: 18, warning_max: 28, critical_min: 15, critical_max: 35, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'prod-02', parameter: 'temperature', warning_min: 18, warning_max: 28, critical_min: 15, critical_max: 35, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'prod-03', parameter: 'temperature', warning_min: 18, warning_max: 28, critical_min: 15, critical_max: 35, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'store-01', parameter: 'temperature', warning_min: 10, warning_max: 30, critical_min: 5, critical_max: 35, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'store-02', parameter: 'temperature', warning_min: 10, warning_max: 30, critical_min: 5, critical_max: 35, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'tech-01', parameter: 'temperature', warning_min: 15, warning_max: 30, critical_min: 10, critical_max: 40, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'tech-02', parameter: 'temperature', warning_min: 15, warning_max: 30, critical_min: 10, critical_max: 40, min_duration_sec: 60, correlation_rules: [], enabled: true },
    
    // Humidity: 30-70% warning, 20-85% critical
    { zone_id: 'prod-01', parameter: 'humidity', warning_min: 30, warning_max: 70, critical_min: 20, critical_max: 85, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'prod-02', parameter: 'humidity', warning_min: 30, warning_max: 70, critical_min: 20, critical_max: 85, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'prod-03', parameter: 'humidity', warning_min: 30, warning_max: 70, critical_min: 20, critical_max: 85, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'store-01', parameter: 'humidity', warning_min: 30, warning_max: 75, critical_min: 20, critical_max: 90, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'store-02', parameter: 'humidity', warning_min: 30, warning_max: 75, critical_min: 20, critical_max: 90, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'tech-01', parameter: 'humidity', warning_min: 20, warning_max: 60, critical_min: 10, critical_max: 70, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'tech-02', parameter: 'humidity', warning_min: 20, warning_max: 60, critical_min: 10, critical_max: 70, min_duration_sec: 60, correlation_rules: [], enabled: true },
    
    // Noise: <70dB warning, <85dB critical (higher is worse)
    { zone_id: 'prod-01', parameter: 'noise', warning_min: null, warning_max: 70, critical_min: null, critical_max: 85, min_duration_sec: 30, correlation_rules: [], enabled: true },
    { zone_id: 'prod-02', parameter: 'noise', warning_min: null, warning_max: 70, critical_min: null, critical_max: 85, min_duration_sec: 30, correlation_rules: [], enabled: true },
    { zone_id: 'prod-03', parameter: 'noise', warning_min: null, warning_max: 70, critical_min: null, critical_max: 85, min_duration_sec: 30, correlation_rules: [], enabled: true },
    { zone_id: 'store-01', parameter: 'noise', warning_min: null, warning_max: 60, critical_min: null, critical_max: 75, min_duration_sec: 30, correlation_rules: [], enabled: true },
    { zone_id: 'store-02', parameter: 'noise', warning_min: null, warning_max: 60, critical_min: null, critical_max: 75, min_duration_sec: 30, correlation_rules: [], enabled: true },
    { zone_id: 'tech-01', parameter: 'noise', warning_min: null, warning_max: 65, critical_min: null, critical_max: 80, min_duration_sec: 30, correlation_rules: [], enabled: true },
    { zone_id: 'tech-02', parameter: 'noise', warning_min: null, warning_max: 65, critical_min: null, critical_max: 80, min_duration_sec: 30, correlation_rules: [], enabled: true },
    
    // Air Quality (MQ135): 0-1000 warning, 0-2000 critical (higher is worse)
    { zone_id: 'prod-01', parameter: 'air_quality', warning_min: null, warning_max: 1000, critical_min: null, critical_max: 2000, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'prod-02', parameter: 'air_quality', warning_min: null, warning_max: 1000, critical_min: null, critical_max: 2000, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'prod-03', parameter: 'air_quality', warning_min: null, warning_max: 1000, critical_min: null, critical_max: 2000, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'store-01', parameter: 'air_quality', warning_min: null, warning_max: 800, critical_min: null, critical_max: 1500, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'store-02', parameter: 'air_quality', warning_min: null, warning_max: 800, critical_min: null, critical_max: 1500, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'tech-01', parameter: 'air_quality', warning_min: null, warning_max: 600, critical_min: null, critical_max: 1200, min_duration_sec: 60, correlation_rules: [], enabled: true },
    { zone_id: 'tech-02', parameter: 'air_quality', warning_min: null, warning_max: 600, critical_min: null, critical_max: 1200, min_duration_sec: 60, correlation_rules: [], enabled: true },
    
    // PM2.5: <15 μg/m³ warning, <35 μg/m³ critical (WHO guidelines)
    { zone_id: 'prod-01', parameter: 'pm25', warning_min: null, warning_max: 15, critical_min: null, critical_max: 35, min_duration_sec: 300, correlation_rules: ['pm10'], enabled: true },
    { zone_id: 'prod-02', parameter: 'pm25', warning_min: null, warning_max: 15, critical_min: null, critical_max: 35, min_duration_sec: 300, correlation_rules: ['pm10'], enabled: true },
    { zone_id: 'prod-03', parameter: 'pm25', warning_min: null, warning_max: 15, critical_min: null, critical_max: 35, min_duration_sec: 300, correlation_rules: ['pm10'], enabled: true },
    { zone_id: 'store-01', parameter: 'pm25', warning_min: null, warning_max: 12, critical_min: null, critical_max: 25, min_duration_sec: 300, correlation_rules: ['pm10'], enabled: true },
    { zone_id: 'store-02', parameter: 'pm25', warning_min: null, warning_max: 12, critical_min: null, critical_max: 25, min_duration_sec: 300, correlation_rules: ['pm10'], enabled: true },
    { zone_id: 'tech-01', parameter: 'pm25', warning_min: null, warning_max: 10, critical_min: null, critical_max: 20, min_duration_sec: 300, correlation_rules: ['pm10'], enabled: true },
    { zone_id: 'tech-02', parameter: 'pm25', warning_min: null, warning_max: 10, critical_min: null, critical_max: 20, min_duration_sec: 300, correlation_rules: ['pm10'], enabled: true },
    
    // PM10: <50 μg/m³ warning, <100 μg/m³ critical
    { zone_id: 'prod-01', parameter: 'pm10', warning_min: null, warning_max: 50, critical_min: null, critical_max: 100, min_duration_sec: 300, correlation_rules: ['pm25'], enabled: true },
    { zone_id: 'prod-02', parameter: 'pm10', warning_min: null, warning_max: 50, critical_min: null, critical_max: 100, min_duration_sec: 300, correlation_rules: ['pm25'], enabled: true },
    { zone_id: 'prod-03', parameter: 'pm10', warning_min: null, warning_max: 50, critical_min: null, critical_max: 100, min_duration_sec: 300, correlation_rules: ['pm25'], enabled: true },
    { zone_id: 'store-01', parameter: 'pm10', warning_min: null, warning_max: 40, critical_min: null, critical_max: 80, min_duration_sec: 300, correlation_rules: ['pm25'], enabled: true },
    { zone_id: 'store-02', parameter: 'pm10', warning_min: null, warning_max: 40, critical_min: null, critical_max: 80, min_duration_sec: 300, correlation_rules: ['pm25'], enabled: true },
    { zone_id: 'tech-01', parameter: 'pm10', warning_min: null, warning_max: 30, critical_min: null, critical_max: 60, min_duration_sec: 300, correlation_rules: ['pm25'], enabled: true },
    { zone_id: 'tech-02', parameter: 'pm10', warning_min: null, warning_max: 30, critical_min: null, critical_max: 60, min_duration_sec: 300, correlation_rules: ['pm25'], enabled: true },
    
    // Voltage: 220-240V normal, 200-260V warning, 190-270V critical
    { zone_id: 'prod-01', parameter: 'voltage', warning_min: 200, warning_max: 260, critical_min: 190, critical_max: 270, min_duration_sec: 10, correlation_rules: [], enabled: true },
    { zone_id: 'prod-02', parameter: 'voltage', warning_min: 200, warning_max: 260, critical_min: 190, critical_max: 270, min_duration_sec: 10, correlation_rules: [], enabled: true },
    { zone_id: 'prod-03', parameter: 'voltage', warning_min: 200, warning_max: 260, critical_min: 190, critical_max: 270, min_duration_sec: 10, correlation_rules: [], enabled: true },
    { zone_id: 'store-01', parameter: 'voltage', warning_min: 200, warning_max: 260, critical_min: 190, critical_max: 270, min_duration_sec: 10, correlation_rules: [], enabled: true },
    { zone_id: 'store-02', parameter: 'voltage', warning_min: 200, warning_max: 260, critical_min: 190, critical_max: 270, min_duration_sec: 10, correlation_rules: [], enabled: true },
    { zone_id: 'tech-01', parameter: 'voltage', warning_min: 210, warning_max: 250, critical_min: 200, critical_max: 260, min_duration_sec: 10, correlation_rules: [], enabled: true },
    { zone_id: 'tech-02', parameter: 'voltage', warning_min: 210, warning_max: 250, critical_min: 200, critical_max: 260, min_duration_sec: 10, correlation_rules: [], enabled: true },
];

alertRules.forEach(rule => {
    db.alert_rules.updateOne(
        { zone_id: rule.zone_id, parameter: rule.parameter },
        { $setOnInsert: { ...rule, created_at: new Date(), updated_at: new Date() } },
        { upsert: true }
    });
});
print('Seeded default alert rules for 7 zones × 7 parameters');

// Seed: Initial Audit Log Entry
const initialAudit = {
    timestamp: new Date(),
    actor_id: 'system',
    actor_role: 'system',
    action: 'initialize',
    resource_type: 'database',
    resource_id: 'env_monitoring',
    details: { message: 'Database initialized with seed data' },
    ip_address: '127.0.0.1',
    user_agent: 'init-mongo.js',
    prev_hash: '0'.repeat(64),
    hash: ''
};
initialAudit.hash = SHA256(initialAudit.prev_hash + JSON.stringify({
    timestamp: initialAudit.timestamp,
    actor_id: initialAudit.actor_id,
    action: initialAudit.action,
    resource_type: initialAudit.resource_type,
    resource_id: initialAudit.resource_id,
    details: initialAudit.details
}));
db.audit_logs.insertOne(initialAudit);
print('Seeded initial audit log entry');

print('=== MongoDB Initialization Complete ===');