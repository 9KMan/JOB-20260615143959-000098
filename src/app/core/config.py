# src/app/core/config.py
"""
Application Configuration.
All settings loaded from environment variables with validation.
"""
import os
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application
    APP_NAME: str = "Scraping Infrastructure"
    DEBUG: bool = Field(default=False, validation_alias="DEBUG")
    ENVIRONMENT: str = Field(default="production", validation_alias="ENVIRONMENT")
    API_VERSION: str = "v1"
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://scraper:scraper@postgres:5432/scraping",
        validation_alias="DATABASE_URL"
    )
    DATABASE_POOL_SIZE: int = Field(default=20, validation_alias="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, validation_alias="DATABASE_MAX_OVERFLOW")
    
    # RabbitMQ
    RABBITMQ_URL: str = Field(
        default="amqp://scraper:scraper@rabbitmq:5672/",
        validation_alias="RABBITMQ_URL"
    )
    RABBITMQ_POOL_SIZE: int = Field(default=10, validation_alias="RABBITMQ_POOL_SIZE")
    
    # Queue Names
    SCRAPE_QUEUE: str = "scraping.jobs"
    RETRY_QUEUE: str = "scraping.retry"
    DEAD_LETTER_QUEUE: str = "scraping.dead_letter"
    MANUAL_REVIEW_QUEUE: str = "scraping.manual_review"
    
    # Retry Configuration
    MAX_RETRIES: int = Field(default=3, validation_alias="MAX_RETRIES")
    RETRY_DELAY_BASE: int = Field(default=5, validation_alias="RETRY_DELAY_BASE")
    RETRY_DELAY_MAX: int = Field(default=300, validation_alias="RETRY_DELAY_MAX")
    CIRCUIT_BREAKER_THRESHOLD: int = Field(default=5, validation_alias="CIRCUIT_BREAKER_THRESHOLD")
    CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, validation_alias="CIRCUIT_BREAKER_TIMEOUT")
    
    # Oxylabs Proxy
    OXYLABS_USERNAME: str = Field(validation_alias="OXYLABS_USERNAME")
    OXYLABS_PASSWORD: str = Field(validation_alias="OXYLABS_PASSWORD")
    OXYLABS_API_URL: str = Field(
        default="http://pr.oxylabs.io:7777",
        validation_alias="OXYLABS_API_URL"
    )
    OXYLABS_SESSION_TIMEOUT: int = Field(default=300, validation_alias="OXYLABS_SESSION_TIMEOUT")
    PROXY_HEALTH_CHECK_INTERVAL: int = Field(default=60, validation_alias="PROXY_HEALTH_CHECK_INTERVAL")
    PROXY_MAX_FAILURES: int = Field(default=3, validation_alias="PROXY_MAX_FAILURES")
    
    # Playwright/Chromium
    CHROMIUM_HEADLESS: bool = Field(default=False, validation_alias="CHROMIUM_HEADLESS")
    CHROMIUM_ARGS: List[str] = Field(
        default=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
        ],
        validation_alias="CHROMIUM_ARGS"
    )
    PAGE_LOAD_TIMEOUT: int = Field(default=30000, validation_alias="PAGE_LOAD_TIMEOUT")
    NAVIGATION_TIMEOUT: int = Field(default=60000, validation_alias="NAVIGATION_TIMEOUT")
    ELEMENT_WAIT_TIMEOUT: int = Field(default=10000, validation_alias="ELEMENT_WAIT_TIMEOUT")
    
    # Xvfb
    XVFB_DISPLAY: str = Field(default=":99", validation_alias="XVFB_DISPLAY")
    XVFB_RESOLUTION: str = Field(default="1920x1080x24", validation_alias="XVFB_RESOLUTION")
    
    # Stealth Settings
    STEALTH_MODE: bool = Field(default=True, validation_alias="STEALTH_MODE")
    FAKE_NAVIGATOR_WEBDRIVER: bool = Field(default=False, validation_alias="FAKE_NAVIGATOR_WEBDRIVER")
    FAKE_NAVIGATOR_PLUGINS: bool = Field(default=True, validation_alias="FAKE_NAVIGATOR_PLUGINS")
    FAKE_NAVIGATOR_LANGUAGES: bool = Field(default=True, validation_alias="FAKE_NAVIGATOR_LANGUAGES")
    
    # LLM Integration
    LLM_PROVIDER: str = Field(default="openai", validation_alias="LLM_PROVIDER")
    OPENAI_API_KEY: str = Field(default="", validation_alias="OPENAI_API_KEY")
    ANTHROPIC_API_KEY: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    LLM_MODEL: str = Field(default="gpt-4", validation_alias="LLM_MODEL")
    LLM_TEMPERATURE: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    LLM_MAX_TOKENS: int = Field(default=1000, validation_alias="LLM_MAX_TOKENS")
    LLM_CACHE_ENABLED: bool = Field(default=True, validation_alias="LLM_CACHE_ENABLED")
    LLM_COST_LIMIT: float = Field(default=100.0, validation_alias="LLM_COST_LIMIT")
    
    # Payment/Quality Thresholds
    SUCCESS_THRESHOLD: float = Field(default=0.95, validation_alias="SUCCESS_THRESHOLD")
    VALIDITY_THRESHOLD: float = Field(default=0.98, validation_alias="VALIDITY_THRESHOLD")
    QUALITY_BONUS_THRESHOLD: float = Field(default=0.98, validation_alias="QUALITY_BONUS_THRESHOLD")
    QUALITY_BONUS_RATE: float = Field(default=0.1, validation_alias="QUALITY_BONUS_RATE")
    TERMINAL_ERROR_CREDIT_RATE: float = Field(default=0.5, validation_alias="TERMINAL_ERROR_CREDIT_RATE")
    
    # Worker Configuration
    WORKER_CONCURRENCY: int = Field(default=2, validation_alias="WORKER_CONCURRENCY")
    WORKER_PREFETCH_COUNT: int = Field(default=1, validation_alias="WORKER_PREFETCH_COUNT")
    
    # Monitoring
    METRICS_ENABLED: bool = Field(default=True, validation_alias="METRICS_ENABLED")
    PROMETHEUS_PORT: int = Field(default=9090, validation_alias="PROMETHEUS_PORT")
    
    # JWT Authentication
    SECRET_KEY: str = Field(validation_alias="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
