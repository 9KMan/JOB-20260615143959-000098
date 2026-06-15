// src/core/config.py
"""Configuration management with environment variable support."""
import os
from functools import lru_cache
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = Field(default="postgresql://postgres:postgres@localhost:5432/scraping")
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    echo: bool = False


class RabbitMQConfig(BaseModel):
    """RabbitMQ configuration."""
    url: str = Field(default="amqp://guest:guest@localhost:5672/")
    exchange_name: str = "scraping.direct"
    dlx_exchange_name: str = "scraping.dlx"
    primary_queue: str = "scraping.work.primary"
    retry_queue: str = "scraping.work.retry"
    dead_queue: str = "scraping.work.dead"
    prefetch_count: int = 1


class JWTConfig(BaseModel):
    """JWT authentication configuration."""
    secret_key: str = Field(default="your-secret-key-change-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours
    refresh_token_expire_days: int = 7


class ProxyConfig(BaseModel):
    """Oxylabs proxy configuration."""
    username: str = ""
    password: str = ""
    endpoint: str = "http://pr.oxylabs.io:7777"
    session_timeout: int = 180  # seconds
    max_retries: int = 3


class BrowserConfig(BaseModel):
    """Playwright browser configuration."""
    headless: bool = True
    browser_type: str = "chromium"
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    stealth_mode: bool = True
    page_timeout: int = 30000  # milliseconds
    navigation_timeout: int = 60000


class WorkerConfig(BaseModel):
    """Worker configuration."""
    concurrency: int = 2
    max_retries: int = 5
    retry_base_delay: int = 5  # seconds
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 30


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""
    enabled: bool = True
    requests_per_minute: int = 100
    burst_size: int = 20


class LLMCfg(BaseModel):
    """LLM processing configuration."""
    provider: str = "openai"  # openai, anthropic, ollama
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.1
    batch_size: int = 10


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "Scraping Platform"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    
    # CORS
    cors_origins: List[str] = ["*"]
    
    # Configuration objects
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    rabbitmq: RabbitMQConfig = Field(default_factory=RabbitMQConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    llm: LLMCfg = Field(default_factory=LLMCfg)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
        
    @validator("environment")
    def validate_environment(cls, v):
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings
