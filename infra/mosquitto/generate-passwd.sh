#!/usr/bin/env bash
# Generate the Mosquitto password file from .env.
#
# The host does not need mosquitto_passwd installed: the official image is used
# so hashes are produced by the same implementation the broker validates.
#
# Usage:
#   cp .env.example .env   # edit passwords
#   ./infra/mosquitto/generate-passwd.sh
#
# Environment overrides:
#   ENV_FILE=path/to/.env   MOSQUITTO_IMAGE=eclipse-mosquitto:2
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MOSQ_DIR="$ROOT_DIR/infra/mosquitto"
PASSWD_FILE="$MOSQ_DIR/passwd"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
MOSQUITTO_IMAGE="${MOSQUITTO_IMAGE:-eclipse-mosquitto:2}"
ZONES=(prod-01 prod-02 prod-03 store-01 store-02 tech-01 tech-02)

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Run: cp .env.example .env" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

add_user() {
  local username="$1" password="$2" first="$3"
  if [[ -z "$username" || -z "$password" ]]; then
    echo "ERROR: empty username/password for '$username'" >&2
    exit 1
  fi
  if [[ "$password" == CHANGE_ME* || ${#password} -lt 12 ]]; then
    echo "ERROR: weak or placeholder password for '$username' (min 12 chars, no CHANGE_ME)" >&2
    exit 1
  fi
  docker run --rm \
    -v "$MOSQ_DIR:/work" \
    -e MQ_USER="$username" \
    -e MQ_PASS="$password" \
    -e MQ_FIRST="$first" \
    "$MOSQUITTO_IMAGE" sh -c '
      if [ "$MQ_FIRST" = "1" ]; then
        mosquitto_passwd -b -c /work/passwd "$MQ_USER" "$MQ_PASS"
      else
        mosquitto_passwd -b /work/passwd "$MQ_USER" "$MQ_PASS"
      fi'
}

echo "Generating $PASSWD_FILE"
rm -f "$PASSWD_FILE"

add_user "${MQTT_BACKEND_USER:-backend}" "${MQTT_BACKEND_PASSWORD:-}" 1
add_user "${MQTT_SIMULATOR_USER:-simulator}" "${MQTT_SIMULATOR_PASSWORD:-}" 0

for zone in "${ZONES[@]}"; do
  var="MQTT_DEVICE_PASSWORD_$(echo "$zone" | tr '[:lower:]-' '[:upper:]_')"
  add_user "esp32-$zone" "${!var:-}" 0
done

# The broker runs as uid 1883 inside the official image; make the file readable
# only by that uid and root, on both the host and inside the container.
docker run --rm -v "$MOSQ_DIR:/work" --user 0 "$MOSQUITTO_IMAGE" \
  sh -c 'chown 1883:1883 /work/passwd && chmod 640 /work/passwd'

USER_COUNT="$(docker run --rm -v "$MOSQ_DIR:/work" --user 1883 "$MOSQUITTO_IMAGE" \
  sh -c 'test -r /work/passwd && grep -c ":" /work/passwd')" || {
    echo "ERROR: generated passwd is not readable by uid 1883" >&2
    exit 1
  }

echo "OK: $USER_COUNT accounts written (contents redacted)."
