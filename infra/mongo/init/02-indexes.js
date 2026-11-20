/* Index creation, idempotent. Mirrors docs/03-database-design.md §3–§13.
 *
 * A failed unique-index build aborts initialization on purpose: silently
 * continuing would leave duplicate identities in a production database.
 */
const dbName = process.env.MONGO_DB || "env_monitoring";
const targetDb = db.getSiblingDB(dbName);

let created = 0;
function idx(collection, keys, options) {
  const opts = options || {};
  const name = opts.name || undefined;
  targetDb.getCollection(collection).createIndex(keys, opts);
  created += 1;
  print(`[init] 02-indexes: ${collection}.${name || "(auto)"} ok`);
}

// --- users -----------------------------------------------------------------
idx("users", { email: 1 }, { unique: true, name: "uniq_email" });
idx("users", { username: 1 }, { unique: true, name: "uniq_username" });
idx("users", { role: 1, is_active: 1 }, { name: "role_active" });
idx("users", { is_active: 1, last_login_at: -1 }, { name: "dormant_review" });

// --- zones -----------------------------------------------------------------
idx("zones", { zone_id: 1 }, { unique: true, name: "uniq_zone_id" });
idx("zones", { type: 1, status: 1 }, { name: "type_status" });
idx("zones", { display_order: 1 }, { name: "display_order" });

// --- devices ---------------------------------------------------------------
idx("devices", { device_id: 1 }, { unique: true, name: "uniq_device_id" });
idx("devices", { mqtt_client_id: 1 }, { unique: true, name: "uniq_mqtt_client_id" });
idx("devices", { zone_id: 1, status: 1 }, { name: "zone_status" });
idx("devices", { status: 1, last_seen_at: 1 }, { name: "offline_sweeper" });
idx("devices", { zone_id: 1, name: 1 }, { name: "zone_name" });

// --- measurements (time-series) -------------------------------------------
idx(
  "measurements",
  { "meta.zone_id": 1, "meta.parameter": 1, timestamp: -1 },
  { name: "zone_parameter_time" },
);
idx("measurements", { "meta.device_id": 1, timestamp: -1 }, { name: "device_time" });
idx("measurements", { "meta.zone_id": 1, timestamp: -1 }, { name: "zone_time" });

// --- alert_rules -----------------------------------------------------------
idx("alert_rules", { rule_id: 1 }, { unique: true, name: "uniq_rule_id" });
idx(
  "alert_rules",
  { zone_id: 1, parameter: 1, direction: 1 },
  { unique: true, name: "uniq_zone_parameter_direction" },
);
idx("alert_rules", { enabled: 1, zone_id: 1, parameter: 1 }, { name: "active_rule_cache" });
idx("alert_rules", { zone_id: 1, updated_at: -1 }, { name: "zone_updated" });

// --- alerts ----------------------------------------------------------------
idx("alerts", { alert_id: 1 }, { unique: true, name: "uniq_alert_id" });
idx(
  "alerts",
  { dedup_key: 1 },
  {
    unique: true,
    name: "uniq_active_dedup_key",
    partialFilterExpression: { active: true },
  },
);
idx("alerts", { status: 1, triggered_at: -1 }, { name: "inbox" });
idx("alerts", { zone_id: 1, triggered_at: -1 }, { name: "zone_history" });
idx("alerts", { level: 1, status: 1, triggered_at: -1 }, { name: "level_queue" });
idx("alerts", { acknowledged_by: 1, acknowledged_at: -1 }, { name: "ack_activity" });

// --- ai_predictions --------------------------------------------------------
idx("ai_predictions", { prediction_id: 1 }, { unique: true, name: "uniq_prediction_id" });
idx("ai_predictions", { zone_id: 1, created_at: -1 }, { name: "zone_latest" });
idx(
  "ai_predictions",
  { zone_id: 1, parameter: 1, created_at: -1 },
  { name: "zone_parameter_latest" },
);
idx("ai_predictions", { prediction_type: 1, created_at: -1 }, { name: "type_latest" });
idx(
  "ai_predictions",
  { "model.name": 1, "model.version": 1, created_at: -1 },
  { name: "model_version_latest" },
);
idx(
  "ai_predictions",
  { expires_at: 1 },
  { name: "ttl_expires_at", expireAfterSeconds: 0 },
);

// --- risk_scores -----------------------------------------------------------
idx("risk_scores", { score_id: 1 }, { unique: true, name: "uniq_score_id" });
idx("risk_scores", { zone_id: 1, computed_at: -1 }, { name: "zone_computed" });
idx(
  "risk_scores",
  { zone_id: 1, window_start: 1 },
  { unique: true, name: "uniq_zone_window" },
);
idx("risk_scores", { level: 1, computed_at: -1 }, { name: "level_computed" });
idx("risk_scores", { expires_at: 1 }, { name: "ttl_expires_at", expireAfterSeconds: 0 });

// --- reports ---------------------------------------------------------------
idx("reports", { report_id: 1 }, { unique: true, name: "uniq_report_id" });
idx("reports", { requested_by: 1, created_at: -1 }, { name: "my_reports" });
idx("reports", { type: 1, created_at: -1 }, { name: "catalog" });
idx("reports", { status: 1, created_at: 1 }, { name: "worker_queue" });
idx("reports", { zone_ids: 1, created_at: -1 }, { name: "zone_reports" });
idx("reports", { expires_at: 1 }, { name: "ttl_expires_at", expireAfterSeconds: 0 });

// --- audit_logs (no TTL; archived after 2 years) ---------------------------
idx("audit_logs", { audit_id: 1 }, { unique: true, name: "uniq_audit_id" });
idx("audit_logs", { timestamp: -1 }, { name: "feed" });
idx("audit_logs", { "actor.user_id": 1, timestamp: -1 }, { name: "actor_feed" });
idx("audit_logs", { action: 1, timestamp: -1 }, { name: "action_feed" });
idx(
  "audit_logs",
  { "resource.type": 1, "resource.id": 1, timestamp: -1 },
  { name: "resource_feed" },
);
idx("audit_logs", { zone_id: 1, timestamp: -1 }, { name: "zone_feed" });

print(`[init] 02-indexes: ${created} index builds submitted on '${dbName}'`);
