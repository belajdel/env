/* Create the least-privilege application user.
 *
 * Runs once, only when the MongoDB data directory is empty (official image
 * docker-entrypoint-initdb.d behaviour). Root credentials come from
 * MONGO_INITDB_ROOT_USERNAME/PASSWORD; the app user comes from:
 *   MONGO_APP_USER, MONGO_APP_PASSWORD, MONGO_DB
 */
const dbName = process.env.MONGO_DB || "env_monitoring";
const appUser = process.env.MONGO_APP_USER;
const appPassword = process.env.MONGO_APP_PASSWORD;
const appDb = db.getSiblingDB(dbName);

if (!appUser || !appPassword) {
  print(`[init] 00-users: MONGO_APP_USER/MONGO_APP_PASSWORD not set, skipping app user`);
} else {
  let existing = null;
  try {
    existing = appDb.getUser(appUser);
  } catch (err) {
    existing = null;
  }
  if (existing) {
    print(`[init] 00-users: user '${appUser}' already exists, leaving it unchanged`);
  } else {
    appDb.createUser({
      user: appUser,
      pwd: appPassword,
      roles: [{ role: "readWrite", db: dbName }],
    });
    print(`[init] 00-users: created '${appUser}' with readWrite on '${dbName}'`);
  }
}
