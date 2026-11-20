#!/bin/bash
# TLS Certificate Generation Script for Mosquitto
# Generates CA, server certificate, and client certificates for 7 zones + backend + ai-service + dashboard
# Run from env-monitoring/infra/certs/

set -e

CERT_DIR="$(dirname "$0")"
cd "$CERT_DIR"

# Create directory structure
mkdir -p ca server client

# Configuration
CA_SUBJECT="/CN=EnvMonitoring-CA/O=Industrial Monitoring/OU=IoT"
SERVER_SUBJECT="/CN=mosquitto/O=Industrial Monitoring/OU=IoT"
DAYS_VALID=3650  # 10 years for CA, 1 year for others (renewable)

echo "=== Generating CA ==="
openssl genrsa -out ca/ca.key 4096
openssl req -x509 -new -nodes -key ca/ca.key -sha256 -days $DAYS_VALID \
    -out ca/ca.crt -subj "$CA_SUBJECT"

echo "=== Generating Server Certificate ==="
openssl genrsa -out server/server.key 2048
openssl req -new -key server/server.key -out server/server.csr -subj "$SERVER_SUBJECT"

# Server extensions
cat > server/server.ext <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = mosquitto
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

openssl x509 -req -in server/server.csr -CA ca/ca.crt -CAkey ca/ca.key \
    -CAcreateserial -out server/server.crt -days 365 -sha256 -extfile server/server.ext

echo "=== Generating Client Certificates ==="

# Device list: 7 zones + backend + ai-service + dashboard
CLIENTS=("prod-01" "prod-02" "prod-03" "store-01" "store-02" "tech-01" "tech-02" "backend" "ai-service" "dashboard")

for CLIENT in "${CLIENTS[@]}"; do
    echo "Generating certificate for $CLIENT..."
    CLIENT_SUBJECT="/CN=$CLIENT/O=Industrial Monitoring/OU=IoT"
    openssl genrsa -out client/$CLIENT.key 2048
    openssl req -new -key client/$CLIENT.key -out client/$CLIENT.csr -subj "$CLIENT_SUBJECT"
    
    cat > client/$CLIENT.ext <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment
extendedKeyUsage = clientAuth
EOF
    
    openssl x509 -req -in client/$CLIENT.csr -CA ca/ca.crt -CAkey ca/ca.key \
        -CAcreateserial -out client/$CLIENT.crt -days 365 -sha256 -extfile client/$CLIENT.ext
    
    # Create combined PEM for MicroPython (cert + key in one file)
    cat client/$CLIENT.crt client/$CLIENT.key > client/$CLIENT.pem
done

echo "=== Creating password file for Mosquitto ==="
# Generate password file (passwords should be set via environment or config)
# This is a template - actual passwords set via mosquitto_passwd in docker-entrypoint
cat > passwd.template <<EOF
# Run: mosquitto_passwd -c /mosquitto/config/passwd <username>
# Then for each user: mosquitto_passwd /mosquitto/config/passwd <username>
# Passwords should be stored in .env and injected at container startup
prod-01:\$6\$...
prod-02:\$6\$...
prod-03:\$6\$...
store-01:\$6\$...
store-02:\$6\$...
tech-01:\$6\$...
tech-02:\$6\$...
backend:\$6\$...
ai-service:\$6\$...
dashboard:\$6\$...
EOF

echo "=== Verifying certificates ==="
openssl verify -CAfile ca/ca.crt server/server.crt
for CLIENT in "${CLIENTS[@]}"; do
    openssl verify -CAfile ca/ca.crt client/$CLIENT.crt
done

echo "=== Setting permissions ==="
chmod 600 ca/ca.key server/server.key client/*.key client/*.pem
chmod 644 ca/ca.crt server/server.crt client/*.crt

echo "=== Done ==="
echo "Certificates generated in:"
echo "  CA: ca/ca.crt, ca/ca.key"
echo "  Server: server/server.crt, server/server.key"
echo "  Clients: client/<name>.crt, client/<name>.key, client/<name>.pem"
echo ""
echo "Copy to mosquitto config:"
echo "  cp ca/ca.crt server/server.crt server/server.key /mosquitto/certs/"
echo "  cp client/*.pem /mosquitto/certs/clients/  (for verification if needed)"