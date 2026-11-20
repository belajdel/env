"""
Backend Configuration
Loads from environment variables with validation via Pydantic Settings.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    APP_NAME: str = "Environmental Monitoring Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # -------------------------------------------------------------------------
    # MongoDB
    # -------------------------------------------------------------------------
    MONGO_URI: str = Field(default="mongodb://admin:mongopass@localhost:27017")
    MONGO_DB: str = "env_monitoring"
    MONGO_MAX_POOL_SIZE: int = 50
    MONGO_MIN_POOL_SIZE: int = 10
    
    # -------------------------------------------------------------------------
    # MQTT
    # -------------------------------------------------------------------------
    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 8883
    MQTT_USERNAME: str = "backend"
    MQTT_PASSWORD: str = "backendpass"
    MQTT_USE_TLS: bool = True
    MQTT_CA_CERT: str = "./certs/ca.crt"
    MQTT_CLIENT_ID: str = "backend-api"
    MQTT_KEEPALIVE: int = 60
    MQTT_QOS: int = 1
    
    # -------------------------------------------------------------------------
    # JWT Authentication
    # -------------------------------------------------------------------------
    JWT_SECRET_KEY: str = Field(default="change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "env-monitoring"
    JWT_AUDIENCE: str = "env-monitoring-api"
    
    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: [
        "http://localhost:8050",
        "http://localhost:8501",
        "http://127.0.0.1:8050",
        "http://127.0.0.1:8501",
    ])
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_REQUESTS: int = 10
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = 60
    RATE_LIMIT_API_REQUESTS: int = 100
    RATE_LIMIT_API_WINDOW_SECONDS: int = 60
    
    # -------------------------------------------------------------------------
    # AI Service
    # -------------------------------------------------------------------------
    AI_SERVICE_URL: str = "http://ai-service:8000"
    AI_SERVICE_TIMEOUT_MS: int = 800
    AI_SERVICE_ENABLED: bool = True
    
    # -------------------------------------------------------------------------
    # WebSocket
    # -------------------------------------------------------------------------
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_MAX_CONNECTIONS_PER_USER: int = 5
    
    # -------------------------------------------------------------------------
    # Reports
    # -------------------------------------------------------------------------
    REPORT_MAX_ROWS: int = 10000
    REPORT_DEFAULT_FORMAT: str = "csv"
    
    # -------------------------------------------------------------------------
    # Seeding
    # -------------------------------------------------------------------------
    SEED_ON_STARTUP: bool = True
    DEFAULT_ADMIN_PASSWORD: str = "Admin123!"
    
    # -------------------------------------------------------------------------
    # Timezone
    # -------------------------------------------------------------------------
    DEFAULT_TIMEZONE: str = "UTC"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Export commonly used settings
settings = get_settings()