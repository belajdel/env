/* Collections, JSON-schema validators and the measurements time-series setup.
 *
 * The backend is the only writer, but validators are a second line of defence
 * (see docs/03-database-design.md). Measurements deliberately have no $jsonSchema
 * validator: MongoDB time-series collections reject validators at creation time,
 * so Pydantic v2 is the enforcement point for that collection.
 *
 * Idempotent: existing collections are left untouched.
 */
const dbName = process.env.MONGO_DB || "env_monitoring";
const targetDb = db.getSiblingDB(dbName);

function ensureCollection(name, options) {
  const infos = targetDb.getCollectionInfos({ name: name });
  if (infos.length > 0) {
    print(`[init] 01-collections: '${name}' already exists`);
    return;
  }
  targetDb.createCollection(name, options || {});
  print(`[init] 01-collections: created '${name}'`);
}

const parameterEnum = [
  "temperature", "humidity", "noise", "air_quality", "pm25", "pm10", "voltage",
];
const zoneIdEnum = [
  "prod-01", "prod-02", "prod-03", "store-01", "store-02", "tech-01", "tech-02",
];

ensureCollection("users", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "email", "username", "password_hash", "role",
        "is_active", "token_version", "created_at", "updated_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        email: { bsonType: "string", pattern: "^[^@\\s]+@[^@\\s]+$" },
        username: { bsonType: "string", minLength: 3, maxLength: 64 },
        password_hash: { bsonType: "string", minLength: 20 },
        full_name: { bsonType: "string" },
        role: { enum: ["admin", "operator", "maintenance", "analyst"] },
        zone_ids: { bsonType: "array", items: { enum: zoneIdEnum } },
        is_active: { bsonType: "bool" },
        token_version: { bsonType: "number", minimum: 0 },
        failed_login_count: { bsonType: "number", minimum: 0 },
        locked_until: { bsonType: ["date", "null"] },
        last_login_at: { bsonType: ["date", "null"] },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("zones", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "zone_id", "name", "type", "status",
        "display_order", "created_at", "updated_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        zone_id: { enum: zoneIdEnum },
        name: { bsonType: "string", minLength: 1, maxLength: 120 },
        type: { enum: ["production", "storage", "technical"] },
        description: { bsonType: "string" },
        timezone: { bsonType: "string" },
        status: { enum: ["active", "maintenance", "decommissioned"] },
        display_order: { bsonType: "number" },
        tags: { bsonType: "array", items: { bsonType: "string" } },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("devices", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "device_id", "zone_id", "status",
        "capabilities", "relays", "created_at", "updated_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        device_id: { bsonType: "string", pattern: "^esp32-[a-z]+-[0-9]{2}$" },
        zone_id: { enum: zoneIdEnum },
        name: { bsonType: "string" },
        hardware_model: { bsonType: "string" },
        firmware_version: { bsonType: "string" },
        mqtt_client_id: { bsonType: "string" },
        mac_address: { bsonType: "string" },
        ip_address: { bsonType: "string" },
        status: { enum: ["online", "offline", "degraded", "maintenance"] },
        last_seen_at: { bsonType: ["date", "null"] },
        capabilities: {
          bsonType: "array",
          items: { enum: [...parameterEnum, "relay", "lcd", "leds"] },
        },
        sensors: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["parameter", "model", "unit"],
            properties: {
              parameter: { enum: parameterEnum },
              model: { bsonType: "string" },
              unit: { bsonType: "string" },
              calibration: { bsonType: "object" },
              warmup_s: { bsonType: "number", minimum: 0 },
            },
          },
        },
        relays: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["relay_id", "name", "gpio", "state", "mode", "fail_safe"],
            properties: {
              relay_id: { enum: [1, 2] },
              name: { bsonType: "string" },
              gpio: { enum: [25, 26] },
              state: { enum: ["on", "off", "unknown"] },
              mode: { enum: ["auto", "manual"] },
              fail_safe: { enum: ["on", "off"] },
              last_command_at: { bsonType: ["date", "null"] },
            },
          },
        },
        health: { bsonType: "object" },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("alert_rules", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "rule_id", "zone_id", "parameter", "direction",
        "enabled", "levels", "version", "created_at", "updated_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        rule_id: { bsonType: "string", minLength: 3 },
        name: { bsonType: "string" },
        zone_id: { enum: zoneIdEnum },
        parameter: { enum: parameterEnum },
        direction: { enum: ["high", "low"] },
        enabled: { bsonType: "bool" },
        levels: { bsonType: "object" },
        predictive: { bsonType: "object" },
        correlations: { bsonType: "array" },
        notification_channels: {
          bsonType: "array",
          items: { enum: ["websocket", "push", "telegram", "email"] },
        },
        cooldown_s: { bsonType: "number", minimum: 0 },
        version: { bsonType: "number", minimum: 1 },
        created_by: { bsonType: ["objectId", "null"] },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("alerts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "alert_id", "dedup_key", "active", "zone_id",
        "parameter", "rule_id", "level", "status", "source",
        "triggered_at", "created_at", "updated_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        alert_id: { bsonType: "string", minLength: 3 },
        dedup_key: { bsonType: "string", minLength: 8 },
        active: { bsonType: "bool" },
        zone_id: { enum: zoneIdEnum },
        device_id: { bsonType: "string" },
        parameter: { enum: parameterEnum },
        rule_id: { bsonType: "string" },
        level: { enum: ["info", "warning", "critical", "predictive"] },
        status: { enum: ["open", "acknowledged", "resolved"] },
        source: { enum: ["threshold", "correlation", "predictive", "manual"] },
        title: { bsonType: "string" },
        message: { bsonType: "string" },
        trigger: { bsonType: "object" },
        risk_score: { bsonType: ["number", "null"], minimum: 0, maximum: 100 },
        first_seen_at: { bsonType: "date" },
        triggered_at: { bsonType: "date" },
        acknowledged_at: { bsonType: ["date", "null"] },
        acknowledged_by: { bsonType: ["objectId", "null"] },
        resolved_at: { bsonType: ["date", "null"] },
        resolved_by: { bsonType: ["objectId", "null"] },
        resolution_note: { bsonType: ["string", "null"] },
        notifications: { bsonType: "array" },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("ai_predictions", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "prediction_id", "zone_id", "parameter",
        "prediction_type", "model", "score", "created_at", "expires_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        prediction_id: { bsonType: "string", minLength: 3 },
        zone_id: { enum: zoneIdEnum },
        device_id: { bsonType: "string" },
        parameter: { enum: parameterEnum },
        prediction_type: { enum: ["anomaly", "threshold_breach"] },
        model: {
          bsonType: "object",
          required: ["name", "version"],
          properties: {
            name: { bsonType: "string" },
            version: { bsonType: "string" },
            framework: { bsonType: "string" },
            artifact_sha256: { bsonType: "string" },
          },
        },
        score: { bsonType: "number" },
        is_anomaly: { bsonType: ["bool", "null"] },
        probability: { bsonType: ["number", "null"] },
        threshold: { bsonType: ["number", "null"] },
        horizon_min: { bsonType: ["number", "null"] },
        expected_value: { bsonType: ["number", "null"] },
        confidence: { bsonType: ["number", "null"] },
        features_window: { bsonType: "object" },
        contributing_factors: { bsonType: "array" },
        risk_contribution: { bsonType: "number" },
        created_at: { bsonType: "date" },
        expires_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("risk_scores", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "score_id", "zone_id", "window_start", "score",
        "level", "components", "computed_at", "expires_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        score_id: { bsonType: "string", minLength: 3 },
        zone_id: { enum: zoneIdEnum },
        window_start: { bsonType: "date" },
        score: { bsonType: "number", minimum: 0, maximum: 100 },
        level: { enum: ["low", "moderate", "high", "critical"] },
        previous_score: { bsonType: ["number", "null"] },
        delta: { bsonType: ["number", "null"] },
        components: { bsonType: "object" },
        drivers: { bsonType: "array" },
        model_version: { bsonType: "string" },
        computed_at: { bsonType: "date" },
        valid_until: { bsonType: "date" },
        expires_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("reports", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "report_id", "type", "format", "zone_ids",
        "status", "created_at", "expires_at",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        report_id: { bsonType: "string", minLength: 3 },
        type: { enum: ["daily", "weekly_ai", "incident", "custom"] },
        format: { enum: ["pdf", "csv", "json"] },
        zone_ids: { bsonType: "array", items: { enum: zoneIdEnum } },
        period: { bsonType: "object" },
        status: { enum: ["queued", "generating", "completed", "failed"] },
        requested_by: { bsonType: ["objectId", "null"] },
        summary: { bsonType: "object" },
        file: { bsonType: ["object", "null"] },
        error: { bsonType: ["string", "null"] },
        created_at: { bsonType: "date" },
        generated_at: { bsonType: ["date", "null"] },
        expires_at: { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

ensureCollection("audit_logs", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "schema_version", "audit_id", "timestamp", "actor", "action",
        "outcome", "prev_hash", "hash",
      ],
      properties: {
        schema_version: { bsonType: "number" },
        audit_id: { bsonType: "string", minLength: 3 },
        timestamp: { bsonType: "date" },
        actor: {
          bsonType: "object",
          required: ["user_id", "role"],
          properties: {
            user_id: { bsonType: ["objectId", "null"] },
            email: { bsonType: "string" },
            role: { enum: ["admin", "operator", "maintenance", "analyst", "system"] },
            ip: { bsonType: "string" },
            user_agent: { bsonType: "string" },
          },
        },
        action: { bsonType: "string", minLength: 3 },
        resource: { bsonType: "object" },
        zone_id: { bsonType: "string" },
        outcome: { enum: ["success", "failure", "denied"] },
        request_id: { bsonType: "string" },
        changes: { bsonType: "object" },
        metadata: { bsonType: "object" },
        prev_hash: { bsonType: "string" },
        hash: { bsonType: "string", pattern: "^[0-9a-f]{64}$" },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});

/* Time-series collection: 10 s samples, 24-month retention.
 * No validator (unsupported on time-series creation); Pydantic owns validation.
 */
const measurementInfos = targetDb.getCollectionInfos({ name: "measurements" });
if (measurementInfos.length > 0) {
  print(`[init] 01-collections: 'measurements' already exists`);
} else {
  targetDb.createCollection("measurements", {
    timeseries: {
      timeField: "timestamp",
      metaField: "meta",
      granularity: "seconds",
    },
    expireAfterSeconds: 63072000,
  });
  print("[init] 01-collections: created 'measurements' time-series collection");
}

print(`[init] 01-collections: done on database '${dbName}'`);
