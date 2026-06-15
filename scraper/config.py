# =============================================================================
# Application Configuration
# Uses Pydantic Settings for environment variable management
# =============================================================================

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        case_sensitive=False,
    )
    
    url: str = Field(
        default="postgresql+asyncpg://scraper:scraper@localhost:5432/scraper_db",
        description="Database connection URL",
    )
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=50)
    pool_timeout: int = Field(default=30, ge=1)
    pool_recycle: int = Field(default=3600, ge=0)
    echo: bool = Field(default=False)


class RabbitMQSettings(BaseSettings):
    """RabbitMQ configuration settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="RABBITMQ_",
        case_sensitive=False,
    )
    
    host: str = Field(default="localhost")
    port: int = Field(default=5672, ge=1, le=65535)
    user: str = Field(default="scraper")
    password: str = Field(default="scraper")
    vhost: str = Field(default="/")
    
    # Exchange names
    direct_exchange: str = "scraper.direct"
    dlx_exchange: str = "scraper.dlx"
    retry_exchange: str = "scraper.retry"
    
    # Queue names
    jobs_queue: str = "scraper.jobs"
    retry_queue: str = "scraper.jobs.retry"
    dlq_queue: str = "scraper.jobs.dlq"
    results_queue: str = "scraper.results"
    heartbeat_queue: str = "scraper.heartbeat"
    
    # Consumer settings
    prefetch_count: int = Field(default=1, ge=1)
    heartbeat_interval: int = Field(default=30, ge=1)
    
    @property
    def url(self) -> str:
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/{self.vhost}"


class WorkerSettings(BaseSettings):
    """Worker configuration settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="WORKER_",
        case_sensitive=False,
    )
    
    max_retries: int = Field(default=5, ge=0)
    retry_delay: int = Field(default=30, ge=0)
    job_timeout: int = Field(default=180, ge=1)
    page_load_timeout: int = Field(default=60, ge=1)
    navigation_timeout: int = Field(default=60, ge=1)
    heartbeat_interval: int = Field(default=30, ge=1)


class ProxySettings(BaseSettings):
    """Oxylabs proxy configuration settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="OXYLABS_",
        case_sensitive=False,
    )
    
    username: str = Field(default="")
    password: str = Field(default="")
    default_country: str = Field(default="US")
    session_timeout: int = Field(default=300, ge=60)
    pool_size: int = Field(default=10, ge=1)
    
    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)


class LLMSettings(BaseSettings):
    """LLM provider configuration settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )
    
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4-turbo-preview")
    openai_max_tokens: int = Field(default=4096)
    openai_temperature: float = Field(default=0.1)
    
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-3-sonnet-20240229")
    anthropic_max_tokens: int = Field(default=4096)
    
    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)
    
    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)


class CircuitBreakerSettings(BaseSettings):
    """Circuit breaker configuration settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="CIRCUIT_BREAKER_",
        case_sensitive=False,
    )
    
    failure_threshold: int = Field(default=5, ge=1)
    recovery_timeout: int = Field(default=30, ge=1)
    half_open_max_calls: int = Field(default=3, ge=1)


class APISettings(BaseSettings):
    """API server configuration settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="API_",
        case_sensitive=False,
    )
    
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    workers: int = Field(default=4, ge=1)
    reload: bool = Field(default=False)
    
    # JWT settings
    jwt_secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_minutes: int = Field(default=60)
    
    # CORS settings
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"]
    )


class AppSettings(BaseSettings):
    """Main application settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    app_name: str = Field(default="scraper-framework")
    app_env: str = Field(default="development")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    proxy: ProxySettings = Field(default_factory=ProxySettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    circuit_breaker: CircuitBreakerSettings = Field(default_factory=CircuitBreakerSettings)
    api: APISettings = Field(default_factory=APISettings)
    
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


@lru_cache
def get_settings() -> AppSettings:
    """Get cached settings instance."""
    return AppSettings()


# Global settings instance
settings = get_settings()
