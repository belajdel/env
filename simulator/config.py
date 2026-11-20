"""
Simulator Configuration for Multi-Zone Environmental Monitoring
"""

import os
from typing import Dict, List

# ============================================
# MQTT CONFIGURATION
# ============================================
MQTT_BROKER = os.getenv('MQTT_BROKER', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', '8883'))
MQTT_USE_TLS = os.getenv('MQTT_USE_TLS', 'true').lower() == 'true'

# Per-device credentials (matching firmware)
# In production, these would come from a secure config file or env vars
DEVICE_CREDENTIALS = {
    'prod-01': {'username': 'prod-01', 'password': os.getenv('MQTT_PROD_01_PASS', 'prod01pass')},
    'prod-02': {'username': 'prod-02', 'password': os.getenv('MQTT_PROD_02_PASS', 'prod02pass')},
    'prod-03': {'username': 'prod-03', 'password': os.getenv('MQTT_PROD_03_PASS', 'prod03pass')},
    'store-01': {'username': 'store-01', 'password': os.getenv('MQTT_STORE_01_PASS', 'store01pass')},
    'store-02': {'username': 'store-02', 'password': os.getenv('MQTT_STORE_02_PASS', 'store02pass')},
    'tech-01': {'username': 'tech-01', 'password': os.getenv('MQTT_TECH_01_PASS', 'tech01pass')},
    'tech-02': {'username': 'tech-02', 'password': os.getenv('MQTT_TECH_02_PASS', 'tech02pass')},
}

# TLS Certificates
CA_CERT_PATH = os.getenv('CA_CERT_PATH', './infra/certs/ca/ca.crt')
CLIENT_CERTS_DIR = os.getenv('CLIENT_CERTS_DIR', './infra/certs/client')

# ============================================
# SIMULATION PARAMETERS
# ============================================
SAMPLING_INTERVAL = 10  # seconds
ZONES = ['prod-01', 'prod-02', 'prod-03', 'store-01', 'store-02', 'tech-01', 'tech-02']

# Zone types for different base conditions
ZONE_TYPES = {
    'prod-01': 'production',
    'prod-02': 'production',
    'prod-03': 'production',
    'store-01': 'storage',
    'store-02': 'storage',
    'tech-01': 'technical',
    'tech-02': 'technical',
}

# Base values for each zone type (daily averages)
BASE_VALUES = {
    'production': {
        'temperature': 24.0,
        'humidity': 50.0,
        'noise': 68.0,
        'air_quality': 600.0,
        'pm25': 12.0,
        'pm10': 40.0,
        'voltage': 230.0,
    },
    'storage': {
        'temperature': 20.0,
        'humidity': 55.0,
        'noise': 50.0,
        'air_quality': 400.0,
        'pm25': 8.0,
        'pm10': 30.0,
        'voltage': 230.0,
    },
    'technical': {
        'temperature': 22.0,
        'humidity': 40.0,
        'noise': 60.0,
        'air_quality': 300.0,
        'pm25': 5.0,
        'pm10': 20.0,
        'voltage': 230.0,
    },
}

# Daily variation amplitudes (sinusoidal)
DAILY_AMPLITUDE = {
    'production': {
        'temperature': 3.0,
        'humidity': 10.0,
        'noise': 5.0,
        'air_quality': 150.0,
        'pm25': 3.0,
        'pm10': 10.0,
        'voltage': 5.0,
    },
    'storage': {
        'temperature': 4.0,
        'humidity': 15.0,
        'noise': 8.0,
        'air_quality': 100.0,
        'pm25': 2.0,
        'pm10': 8.0,
        'voltage': 5.0,
    },
    'technical': {
        'temperature': 5.0,
        'humidity': 10.0,
        'noise': 6.0,
        'air_quality': 80.0,
        'pm25': 2.0,
        'pm10': 5.0,
        'voltage': 8.0,
    },
}

# Noise (random variation) standard deviations
NOISE_STD = {
    'temperature': 0.5,
    'humidity': 2.0,
    'noise': 2.0,
    'air_quality': 30.0,
    'pm25': 1.0,
    'pm10': 2.0,
    'voltage': 1.0,
}

# Sensor drift per day (systematic)
DRIFT_PER_DAY = {
    'temperature': 0.01,    # °C/day
    'humidity': 0.05,       # %/day
    'noise': 0.02,          # dB/day
    'air_quality': 1.0,     # ppm/day
    'pm25': 0.01,           # μg/m³/day
    'pm10': 0.02,           # μg/m³/day
    'voltage': 0.005,       # V/day
}

# Parameter units (must match firmware)
PARAMETER_UNITS = {
    'temperature': '°C',
    'humidity': '%',
    'noise': 'dB',
    'air_quality': 'ppm',
    'pm25': 'μg/m³',
    'pm10': 'μg/m³',
    'voltage': 'V',
}

VALID_PARAMETERS = list(PARAMETER_UNITS.keys())

# ============================================
# ANOMALY INJECTION
# ============================================
ANOMALY_TYPES = ['spike', 'drift', 'stuck', 'dropout']

# Default anomaly parameters
ANOMALY_DEFAULTS = {
    'spike': {'magnitude': 3.0, 'duration': 3},      # 3 sigma for 3 samples
    'drift': {'rate': 0.5, 'duration': 60},          # 0.5 sigma/min for 60 min
    'stuck': {'duration': 30},                       # stuck for 30 samples
    'dropout': {'probability': 0.5, 'duration': 10}, # 50% dropout for 10 samples
}

# ============================================
# MQTT TOPICS
# ============================================
TOPIC_TEMPLATE = "factory/{zone_id}/{parameter}"
TOPIC_STATUS_TEMPLATE = "factory/{zone_id}/status"
TOPIC_STATE_TEMPLATE = "factory/{zone_id}/state"

# ============================================
# SIMULATION CONTROL
# ============================================
SEED = 42  # Fixed seed for reproducibility
PUBLISH_QOS = 1
PUBLISH_RETAIN = False  # Measurements not retained
STATUS_RETAIN = True
STATE_RETAIN = True