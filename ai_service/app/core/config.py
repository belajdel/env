"""
AI Service Configuration
Pydantic Settings for environment-based config
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AI Service settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # App
    APP_NAME: str = "Environmental Monitoring AI Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # MongoDB
    MONGO_URI: str = "mongodb://admin:mongopass@mongodb:27017"
    MONGO_DB: str = "env_monitoring"
    
    # MQTT
    MQTT_BROKER: str = "mosquitto"
    MQTT_PORT: int = 8883
    MQTT_USERNAME: str = "ai-service"
    MQTT_PASSWORD: str = "aipass"
    MQTT_USE_TLS: bool = True
    MQTT_CA_CERT: str = "/app/certs/ca.crt"
    
    # Backend
    BACKEND_URL: str = "http://backend:8000"
    
    # Model
    MODEL_DIR: str = "/app/models"
    MODEL_RETRAIN_INTERVAL_HOURS: int = 24
    MODEL_MIN_TRAINING_SAMPLES: int = 1000
    
    # Synthetic data generation
    SYNTHETIC_DATA_SEED: int = 42
    SYNTHETIC_DAYS: int = 365
    SYNTHETIC_SAMPLE_RATE_MINUTES: int = 10
    
    # Training
    TRAIN_TEST_SPLIT_RATIO: float = 0.8
    VALIDATION_SPLIT_RATIO: float = 0.1
    RANDOM_STATE: int = 42
    
    # Model comparison
    MODEL_COMPARISON_METRICS: List[str] = ["precision", "recall", "f1", "roc_auc"]
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])
    
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60


settings = Settings()