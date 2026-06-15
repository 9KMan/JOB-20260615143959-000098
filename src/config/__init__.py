# src/config/__init__.py
"""
Configuration management for the scraping framework.
All settings loaded from environment variables.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration."""
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    name: str = os.getenv("POSTGRES_DB", "scraper")
    user: str = os.getenv("POSTGRES_USER", "scraper")
    password: str = os.getenv("POSTGRES_PASSWORD", "")
    pool_size: int = int(os.getenv("POSTGRES_POOL_SIZE", "10"))
    max_overflow: int = int(os.getenv("POSTGRES_MAX_OVERFLOW", "20"))
    
    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class RabbitMQConfig:
    """RabbitMQ configuration for worker fleet."""
    host: str = os.getenv("RABBITMQ_HOST", "localhost")
    port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    user: str = os.getenv("RABBITMQ_USER", "guest")
    password: str = os.getenv("RABBITMQ_PASSWORD", "guest")
    vhost: str = os.getenv("RABBITMQ_VHOST", "/")
    
    # Queue names
    scrape_queue: str = os.getenv("RABBITMQ_SCRAPE_QUEUE", "scrape_tasks")
    retry_queue: str = os.getenv("RABBITMQ_RETRY_QUEUE", "scrape_tasks_retry")
    dead_letter_queue: str = os.getenv("RABBITMQ_DLQ", "scrape_tasks_dlq")
    completed_queue: str = os.getenv("RABBITMQ_COMPLETED_QUEUE", "scrape_tasks_completed")
    
    # Retry configuration
    max_retries: int = int(os.getenv("RABBITMQ_MAX_RETRIES", "5"))
    retry_delay_seconds: int = int(os.getenv("RABBITMQ_RETRY_DELAY", "30"))
    exponential_backoff: bool = os.getenv("RABBITMQ_EXPONENTIAL_BACKOFF", "true").lower() == "true"
    max_retry_delay: int = int(os.getenv("RABBITMQ_MAX_RETRY_DELAY", "300"))
    
    # Circuit breaker
    circuit_breaker_threshold: int = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "10"))
    circuit_breaker_timeout: int = int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60"))
    
    @property
    def url(self) -> str:
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}/{self.vhost}"


@dataclass
class ProxyConfig:
    """Oxylabs proxy configuration."""
    username: str = os.getenv("OXYLABS_USERNAME", "")
    password: str = os.getenv("OXYLABS_PASSWORD", "")
    session_timeout: int = int(os.getenv("OXYLABS_SESSION_TIMEOUT", "600"))
    
    # Sticky session settings
    sticky_session: bool = os.getenv("OXYLABS_STICKY_SESSION", "true").lower() == "true"
    unique_exit_nodes: bool = os.getenv("OXYLABS_UNIQUE_EXITS", "true").lower() == "true"
    
    # Backoff settings for tunnel errors
    initial_backoff_ms: int = int(os.getenv("PROXY_BACKOFF_INITIAL_MS", "1000"))
    max_backoff_ms: int = int(os.getenv("PROXY_BACKOFF_MAX_MS", "60000"))
    backoff_multiplier: float = float(os.getenv("PROXY_BACKOFF_MULTIPLIER", "2.0"))
    
    # Proxy pool for unique exits
    exit_node_count: int = int(os.getenv("OXYLABS_EXIT_NODE_COUNT", "16"))
    
    def get_proxy_url(self, exit_node: Optional[int] = None) -> str:
        """Generate proxy URL with optional exit node."""
        session_id = f"session_{exit_node or 0}_{os.getpid()}"
        host = f"pr.oxylabs.io"
        if exit_node is not None and self.unique_exit_nodes:
            host = f"customer-{exit_node % self.exit_node_count}- residential.oxylabs.io"
        return f"http://{self.username}-session-{session_id}:{self.password}@{host}:7777"


@dataclass
class BrowserConfig:
    """Playwright/Chromium configuration."""
    headless: bool = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
    xvfb_display: Optional[str] = os.getenv("XVFB_DISPLAY", None)
    
    # Timeouts
    navigation_timeout_ms: int = int(os.getenv("BROWSER_NAV_TIMEOUT_MS", "30000"))
    element_timeout_ms: int = int(os.getenv("BROWSER_ELEMENT_TIMEOUT_MS", "10000"))
    load_state_timeout_ms: int = int(os.getenv("BROWSER_LOAD_STATE_TIMEOUT_MS", "5000"))
    
    # Viewport
    viewport_width: int = int(os.getenv("BROWSER_VIEWPORT_WIDTH", "1920"))
    viewport_height: int = int(os.getenv("BROWSER_VIEWPORT_HEIGHT", "1080"))
    
    # Stealth settings
    stealth_mode: bool = os.getenv("BROWSER_STEALTH", "true").lower() == "true"
    disable_web_security: bool = os.getenv("BROWSER_DISABLE_WEB_SECURITY", "false").lower() == "true"
    
    # User agent
    user_agent: str = os.getenv(
        "BROWSER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Anti-bot mitigation
    accept_cookies: bool = os.getenv("BROWSER_ACCEPT_COOKIES", "true").lower() == "true"
    cookie_banner_selector: str = os.getenv("COOKIE_BANNER_SELECTOR", "[data-testid='cookie-banner'], .cookie-banner, #onetrust-accept-btn-handler")
    skip_captcha_screenshots: bool = os.getenv("SKIP_CAPTCHA_SCREENSHOTS", "true").lower() == "true"


@dataclass
class LLMConfig:
    """LLM post-processing configuration."""
    provider: str = os.getenv("LLM_PROVIDER", "openai")
    api_key: str = os.getenv("LLM_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "gpt-4o")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    
    # Error classification prompt
    error_classification_prompt: str = """
    Analyze the following scraping error and classify it:

    Error Type Categories:
    - TRANSIENT: Network issues, temporary blocks, rate limits (retry recommended)
    - TERMINAL: Permanent blocks, CAPTCHA, site structure changes (do not retry)
    - PROXY: Proxy-specific errors like ERR_TUNNEL (may recover with different exit)
    - ANTI_BOT: Detection triggers, headless fingerprinting (requires stealth fixes)

    Error Details:
    {error_details}

    Site Context:
    {site_context}

    Provide a JSON response with:
    - classification: TRANSIENT | TERMINAL | PROXY | ANTI_BOT
    - confidence: 0.0 - 1.0
    - reasoning: Brief explanation
    - recommended_action: Specific next steps
    """
    
    # Content extraction prompt
    extraction_prompt: str = """
    Extract structured data from the following scraped HTML content.
    
    Target fields: {target_fields}
    
    HTML Content:
    {html_content}
    
    Return valid JSON with the extracted fields.
    """


@dataclass
class WorkerConfig:
    """Worker fleet configuration."""
    worker_id: str = os.getenv("WORKER_ID", f"worker-{os.getpid()}")
    concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "1"))
    prefetch_count: int = int(os.getenv("WORKER_PREFETCH", "1"))
    
    # Heartbeat
    heartbeat_interval: int = int(os.getenv("WORKER_HEARTBEAT_INTERVAL", "30"))
    heartbeat_timeout: int = int(os.getenv("WORKER_HEARTBEAT_TIMEOUT", "120"))
    
    # Graceful shutdown
    shutdown_timeout: int = int(os.getenv("WORKER_SHUTDOWN_TIMEOUT", "30"))
    
    # Metrics
    metrics_enabled: bool = os.getenv("WORKER_METRICS_ENABLED", "true").lower() == "true"
    metrics_port: int = int(os.getenv("WORKER_METRICS_PORT", "9090"))


@dataclass
class AppConfig:
    """Main application configuration."""
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    environment: str = os.getenv("ENVIRONMENT", "production")
    
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    rabbitmq: RabbitMQConfig = field(default_factory=RabbitMQConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables."""
        return cls(
            debug=os.getenv("DEBUG", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            environment=os.getenv("ENVIRONMENT", "production"),
            database=DatabaseConfig(),
            rabbitmq=RabbitMQConfig(),
            proxy=ProxyConfig(),
            browser=BrowserConfig(),
            llm=LLMConfig(),
            worker=WorkerConfig(),
        )


# Global configuration instance
config = AppConfig.from_env()
