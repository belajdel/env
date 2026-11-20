# Setup Guide

## Prerequisites

### System Requirements
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| Disk | 20 GB free | 50+ GB free |
| Docker | 24.0+ | 26.0+ |
| Docker Compose | 2.20+ | 2.24+ |
| OS | Linux/macOS/WSL2 | Linux |

### Ports Required
| Port | Service | Protocol |
|------|---------|----------|
| 8000 | Backend API | HTTP |
| 8001 | AI Service | HTTP |
| 8050 | Dashboard | HTTP |
| 8080 | Mobile PWA | HTTP |
| 8883 | Mosquitto MQTT | TLS |
| 9001 | Mosquitto WebSocket | TLS |
| 27017 | MongoDB | TCP |

---

## Quick Start (Development)

### 1. Clone & Enter Directory
```bash
cd /home/insurgent/env-monitoring
```

### 2. Generate Certificates (First Time Only)
```bash
# Run cert generator (creates CA, server, and client certs)
docker compose --profile setup up cert-generator

# Or manually:
cd infra/certs
chmod +x generate_certs.sh
./generate_certs.sh
```

### 3. Configure Environment
```bash
# Copy template
cp .env.example .env

# Edit with secure values
nano .env
```

**Required Changes in `.env`**:
```bash
# Generate secure secrets (run these commands):
openssl rand -hex 32  # For JWT_SECRET_KEY
openssl rand -hex 32  # For DASH_SECRET_KEY

# MongoDB
MONGO_ROOT_PASSWORD=your_secure_mongo_password

# MQTT Passwords (generate with: mosquitto_passwd -c /dev/null user)
MOSQUITTO_BACKEND_PASSWORD=secure_backend_pass
MOSQUITTO_AI_PASSWORD=secure_ai_pass
MOSQUITTO_DASHBOARD_PASSWORD=secure_dash_pass
MOSQUITTO_PROD_01_PASS=secure_prod01_pass
MOSQUITTO_PROD_02_PASS=secure_prod02_pass
MOSQUITTO_PROD_03_PASS=secure_prod03_pass
MOSQUITTO_STORE_01_PASS=secure_store01_pass
MOSQUITTO_STORE_02_PASS=secure_store02_pass
MOSQUITTO_TECH_01_PASS=secure_tech01_pass
MOSQUITTO_TECH_02_PASS=secure_tech02_pass

# Firebase (for mobile push) - optional
FCM_SERVER_KEY=your_fcm_server_key
FCM_PROJECT_ID=your_firebase_project_id

# Telegram (fallback for push) - optional
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. Start Stack
```bash
# Build and start all services
docker compose up --build -d

# View logs
docker compose logs -f

# Check status
docker compose ps
```

### 5. Verify Services
```bash
# Backend health
curl http://localhost:8000/health

# AI Service health
curl http://localhost:8001/api/v1/health

# Dashboard
curl http://localhost:8050/health

# Mobile
curl http://localhost:8080/health

# MongoDB
docker compose exec mongodb mongosh --eval "db.adminCommand('ping')"

# Mosquitto
docker compose exec mosquitto mosquitto_sub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt -t '$SYS/broker/version' -C 1 -i healthcheck --tls-version tlsv1.2
```

### 6. Access Applications
| Service | URL | Credentials |
|---------|-----|-------------|
| Dashboard | http://localhost:8050 | admin / Admin123! |
| Mobile PWA | http://localhost:8080 | admin / Admin123! |
| Backend API Docs | http://localhost:8000/docs | - |
| AI Service API Docs | http://localhost:8001/docs | - |

---

## Production Deployment

### 1. Server Preparation
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose (v2)
sudo apt install docker-compose-plugin

# Verify
docker compose version
```

### 2. Firewall Configuration
```bash
# Allow only necessary ports
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP (nginx)
sudo ufw allow 443/tcp     # HTTPS (nginx)
sudo ufw allow 8000/tcp    # Backend (internal)
sudo ufw allow 8001/tcp    # AI Service (internal)
sudo ufw allow 8050/tcp    # Dashboard (internal)
sudo ufw allow 8080/tcp    # Mobile (internal)
sudo ufw enable
```

### 3. Reverse Proxy (Nginx + TLS)
```nginx
# /etc/nginx/sites-available/monitoring
server {
    listen 80;
    server_name monitoring.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name monitoring.yourdomain.com;
    
    ssl_certificate /etc/letsencrypt/live/monitoring.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/monitoring.yourdomain.com/privkey.pem;
    
    # Dashboard
    location / {
        proxy_pass http://localhost:8050;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Mobile PWA
    location /mobile/ {
        proxy_pass http://localhost:8080/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # AI Service
    location /ai/ {
        proxy_pass http://localhost:8001/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/monitoring /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Get TLS cert
sudo certbot --nginx -d monitoring.yourdomain.com
```

### 4. Production Environment
```bash
# Copy and secure .env
cp .env.example .env.production
# Edit with production values
# Ensure JWT_SECRET_KEY, DASH_SECRET_KEY, MONGO_ROOT_PASSWORD are strong

# Use production compose override
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'
services:
  backend:
    environment:
      - CORS_ORIGINS=https://monitoring.yourdomain.com
      - LOG_LEVEL=WARNING
    deploy:
      resources:
        limits:
          memory: 1G
  
  ai_service:
    environment:
      - LOG_LEVEL=WARNING
    deploy:
      resources:
        limits:
          memory: 2G
  
  dashboard:
    environment:
      - LOG_LEVEL=WARNING
  
  mongodb:
    deploy:
      resources:
        limits:
          memory: 2G
EOF

# Start production stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

### 5. Monitoring & Logs
```bash
# View all logs
docker compose logs -f --tail=100

# Specific service
docker compose logs -f backend
docker compose logs -f ai_service

# Prometheus metrics
curl http://localhost:8000/metrics
curl http://localhost:8001/api/v1/health

# Disk usage
docker system df
```

---

## ESP32 Firmware Deployment

### 1. Hardware Setup
Follow `docs/esp32_pin_table.md` for wiring.

### 2. Install MicroPython
```bash
# Download latest MicroPython for ESP32
wget https://micropython.org/resources/firmware/esp32-20240101-v1.22.0.bin

# Flash
esptool.py -p /dev/ttyUSB0 -b 460800 write_flash -z 0x1000 esp32-20240101-v1.22.0.bin
```

### 3. Deploy Firmware
```bash
# Using rshell
pip install rshell
rshell -p /dev/ttyUSB0
cp -r firmware/ /pyboard/

# Or using ampy
pip install adafruit-ampy
ampy -p /dev/ttyUSB0 put firmware/main.py /main.py
ampy -p /dev/ttyUSB0 put firmware/sensors/ /sensors/
ampy -p /dev/ttyUSB0 put firmware/mqtt/ /mqtt/
# ... etc
```

### 4. Configure Device Certificates
```bash
# Copy client certs to device
ampy -p /dev/ttyUSB0 mkdir /certs
ampy -p /dev/ttyUSB0 put infra/certs/ca/ca.crt /certs/ca.crt
ampy -p /dev/ttyUSB0 put infra/certs/client/prod-01.crt /certs/client.crt
ampy -p /dev/ttyUSB0 put infra/certs/client/prod-01.key /certs/client.key
```

### 5. Configure Device Settings
Edit `firmware/config.py` on device:
```python
# firmware/config.py
MQTT_BROKER = "your-mqtt-broker.com"
MQTT_PORT = 8883
MQTT_USERNAME = "prod-01"
MQTT_PASSWORD = "secure_prod01_pass"  # From .env
ZONE_ID = "prod-01"
SAMPLING_INTERVAL = 10  # seconds
```

---

## Simulator Usage

### Run Simulator (Docker)
```bash
# Start with stack
docker compose up -d simulator

# Or run manually with anomalies
docker compose exec simulator python -m simulator.main \
  --broker mosquitto --port 8883 --tls \
  --anomaly --zone prod-01 --parameter temperature \
  --duration 60 --type spike
```

### Simulator CLI Options
```bash
python -m simulator.main --help

Options:
  --broker TEXT         MQTT broker hostname [default: mosquitto]
  --port INTEGER        MQTT port [default: 8883]
  --tls / --no-tls      Use TLS [default: true]
  --anomaly             Inject anomaly
  --zone TEXT           Zone for anomaly
  --parameter TEXT      Parameter for anomaly
  --duration INTEGER    Anomaly duration in seconds [default: 300]
  --type TEXT           Anomaly type: spike, drift, drop, stuck, noise_burst
  --interval INTEGER    Sampling interval seconds [default: 10]
  --log-level TEXT      Log level [default: INFO]
```

### Examples
```bash
# Normal simulation (7 zones, 10s interval)
python -m simulator.main --broker localhost --port 8883 --tls

# Inject temperature spike in prod-01 for 5 minutes
python -m simulator.main --broker localhost --port 8883 --tls \
  --anomaly --zone prod-01 --parameter temperature \
  --duration 300 --type spike

# Inject sensor drift in store-02
python -m simulator.main --broker localhost --port 8883 --tls \
  --anomaly --zone store-02 --parameter humidity \
  --duration 600 --type drift

# Stuck sensor simulation
python -m simulator.main --broker localhost --port 8883 --tls \
  --anomaly --zone tech-01 --parameter voltage \
  --duration 120 --type stuck
```

---

## Development Workflow

### Backend Development
```bash
# Enter backend container
docker compose exec backend bash

# Run tests
pytest -q

# Run single test
pytest tests/test_alerts.py::test_critical_alert -v

# Format code
ruff format .
ruff check . --fix

# Type check
mypy app/
```

### AI Service Development
```bash
# Enter AI service container
docker compose exec ai_service bash

# Run tests
pytest -q

# Generate synthetic data
python -m app.services.data_generator

# Train models manually
python -c "from app.services.model_trainer import train_all_models; import asyncio; asyncio.run(train_all_models(force=True))"
```

### Dashboard Development
```bash
# Local development
cd dashboard
pip install -r requirements.txt
python app.py

# Access at http://localhost:8050
```

### Mobile Development
```bash
# Local development
cd mobile
npx serve -s . -l 8080

# Access at http://localhost:8080
# Open DevTools -> Application -> Service Workers to test PWA
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `certificate verify failed` | Run `docker compose --profile setup up cert-generator` |
| `connection refused` on 8883 | Check Mosquitto logs: `docker compose logs mosquitto` |
| `MongoDB connection failed` | Verify MONGO_URI in .env, check MongoDB health |
| `JWT_SECRET_KEY not set` | Generate with `openssl rand -hex 32` and add to .env |
| `AI model not ready` | Wait for training or trigger: `curl -X POST localhost:8001/api/v1/retrain -d '{"force":true}'` |
| `WebSocket connection failed` | Check CORS_ORIGINS includes your origin, verify token |
| `Mobile PWA not installing` | Serve over HTTPS (required for PWA), check manifest.json |

### Debug Commands
```bash
# Check service health
docker compose ps

# View resource usage
docker stats

# Inspect container
docker compose exec backend bash
docker compose exec ai_service bash

# Check logs
docker compose logs --tail=100 backend
docker compose logs --tail=100 ai_service

# Database shell
docker compose exec mongodb mongosh -u admin -p mongopass --authenticationDatabase admin

# MQTT test publish
docker compose exec mosquitto mosquitto_pub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt -t 'factory/prod-01/temperature' -m '{"zone_id":"prod-01","parameter":"temperature","value":25.0,"unit":"°C","timestamp":"2026-01-15T10:30:00Z"}'

# MQTT subscribe
docker compose exec mosquitto mosquitto_sub -h localhost -p 8883 --cafile /mosquitto/certs/ca.crt -t 'factory/#' -v
```

### Reset Everything
```bash
# Stop and remove containers, volumes
docker compose down -v

# Remove images
docker compose down --rmi all

# Clean Docker
docker system prune -a

# Start fresh
docker compose up --build -d
```

---

## Backup & Restore

### MongoDB Backup
```bash
# Backup
docker compose exec mongodb mongodump -u admin -p mongopass --authenticationDatabase admin --out /data/backup/$(date +%F)

# Copy to host
docker cp env-monitoring-mongodb:/data/backup/$(date +%F) ./backups/

# Restore
docker compose exec mongodb mongorestore -u admin -p mongopass --authenticationDatabase admin /data/backup/2026-01-15
```

### Model Backup
```bash
# Models are in ai_models volume
docker run --rm -v env-monitoring_ai_models:/models -v $(pwd)/backups:/backup alpine tar czf /backup/models_$(date +%F).tar.gz -C /models .
```

### Full Backup Script
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%F_%H-%M)
BACKUP_DIR="./backups/$DATE"
mkdir -p $BACKUP_DIR

# MongoDB
docker compose exec -T mongodb mongodump -u admin -p $MONGO_ROOT_PASSWORD --authenticationDatabase admin --archive --gzip > $BACKUP_DIR/mongodb.gz

# Models
docker run --rm -v env-monitoring_ai_models:/models -v $(pwd)/$BACKUP_DIR:/backup alpine tar czf /backup/models.tar.gz -C /models .

# Config
cp .env $BACKUP_DIR/
cp docker-compose.yml $BACKUP_DIR/

echo "Backup saved to $BACKUP_DIR"
```

---

## Updating

### Pull Latest Changes
```bash
git pull

# Rebuild changed services
docker compose up --build -d

# Run migrations if any
docker compose exec backend python -m app.db.migrations
```

### Rolling Update (Zero Downtime)
```bash
# Update backend
docker compose up --build -d --no-deps backend

# Update AI service
docker compose up --build -d --no-deps ai_service

# Update dashboard
docker compose up --build -d --no-deps dashboard
```