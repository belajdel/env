#!/usr/bin/env bash
# Generate the development PKI used by Mosquitto and the ESP32/simulator clients.
#
# Outputs (gitignored):
#   infra/tls/certs/ca.crt        project CA certificate (copy to devices)
#   infra/tls/certs/ca.key        CA private key (keep offline in production)
#   infra/tls/certs/server.crt    broker certificate
#   infra/tls/certs/server.key    broker private key
#
# Usage:
#   ./infra/tls/generate-certs.sh            # create if missing
#   ./infra/tls/generate-certs.sh --force    # rotate everything
#
# The server certificate always covers localhost, mosquitto and 127.0.0.1.
# Add the broker's LAN address (or DNS name) when devices connect over Wi-Fi:
#   EXTRA_SAN="IP:192.168.10.10,DNS:broker.factory.local" ./infra/tls/generate-certs.sh --force
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERT_DIR="$ROOT_DIR/infra/tls/certs"
CA_DAYS=3650
SERVER_DAYS=825
EXTRA_SAN="${EXTRA_SAN:-}"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

mkdir -p "$CERT_DIR"
# 755 so the broker (uid 1883) can traverse; files themselves stay restricted.
chmod 755 "$CERT_DIR"

if [[ -f "$CERT_DIR/server.crt" && -f "$CERT_DIR/server.key" && -f "$CERT_DIR/ca.crt" && $FORCE -eq 0 ]]; then
  echo "Certificates already exist in $CERT_DIR (use --force to rotate)."
else
  echo "Generating CA and server certificate in $CERT_DIR"
  rm -f "$CERT_DIR"/ca.key "$CERT_DIR"/ca.crt "$CERT_DIR"/ca.srl \
        "$CERT_DIR"/server.key "$CERT_DIR"/server.csr "$CERT_DIR"/server.crt \
        "$CERT_DIR"/server.ext

  openssl req -x509 -newkey rsa:4096 -sha256 -days "$CA_DAYS" -nodes \
    -keyout "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt" \
    -subj "/CN=env-monitoring-dev-ca/O=Env Monitoring Dev" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" >/dev/null 2>&1

  openssl req -new -newkey rsa:2048 -sha256 -nodes \
    -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.csr" \
    -subj "/CN=mosquitto/O=Env Monitoring Dev" >/dev/null 2>&1

  SAN="DNS:localhost,DNS:mosquitto,IP:127.0.0.1"
  if [[ -n "$EXTRA_SAN" ]]; then
    SAN="$SAN,$EXTRA_SAN"
  fi

  cat > "$CERT_DIR/server.ext" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=$SAN
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

  openssl x509 -req -in "$CERT_DIR/server.csr" -CA "$CERT_DIR/ca.crt" \
    -CAkey "$CERT_DIR/ca.key" -CAcreateserial -out "$CERT_DIR/server.crt" \
    -days "$SERVER_DAYS" -sha256 -extfile "$CERT_DIR/server.ext" >/dev/null 2>&1

  rm -f "$CERT_DIR/server.csr" "$CERT_DIR/server.ext"
  chmod 600 "$CERT_DIR/ca.key"
  chmod 640 "$CERT_DIR/server.key"
  chmod 644 "$CERT_DIR/ca.crt" "$CERT_DIR/server.crt"
  echo "New CA and server certificate created."
fi

# Sanity checks: chain, hostname coverage, key match.
openssl verify -CAfile "$CERT_DIR/ca.crt" "$CERT_DIR/server.crt" >/dev/null
openssl x509 -in "$CERT_DIR/server.crt" -noout -checkhost localhost >/dev/null
KEY_MOD="$(openssl rsa -in "$CERT_DIR/server.key" -noout -modulus 2>/dev/null | openssl sha256)"
CRT_MOD="$(openssl x509 -in "$CERT_DIR/server.crt" -noout -modulus 2>/dev/null | openssl sha256)"
[[ "$KEY_MOD" == "$CRT_MOD" ]] || { echo "ERROR: server key does not match certificate" >&2; exit 1; }

# The broker runs as uid 1883 in the official image and must read the server key.
if command -v docker >/dev/null 2>&1; then
  docker run --rm -v "$CERT_DIR:/certs" --user 0 "${MOSQUITTO_IMAGE:-eclipse-mosquitto:2}" \
    sh -c 'chown 1883:1883 /certs/server.key /certs/ca.crt /certs/server.crt && chmod 640 /certs/server.key' >/dev/null
else
  echo "WARNING: docker not found; chown server.key to uid 1883 before starting the broker." >&2
fi

# Make the CA available to the firmware tree so it can be copied to the device.
if [[ -d "$ROOT_DIR/firmware" ]]; then
  mkdir -p "$ROOT_DIR/firmware/certs"
  cp "$CERT_DIR/ca.crt" "$ROOT_DIR/firmware/certs/ca.crt"
  echo "Copied CA to firmware/certs/ca.crt (flash this file to /certs/ca.crt on the device)."
fi

echo
echo "CA SHA-256 fingerprint:"
openssl x509 -in "$CERT_DIR/ca.crt" -noout -fingerprint -sha256 | sed 's/^/  /'
echo "Server SAN:"
openssl x509 -in "$CERT_DIR/server.crt" -noout -ext subjectAltName | sed 's/^/  /'
