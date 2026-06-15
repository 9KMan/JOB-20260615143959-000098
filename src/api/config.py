// src/api/config.py
"""API-specific configuration."""
from typing import List, Optional
from pydantic import BaseModel, Field


class APIConfig(BaseModel):
    """API server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False
    log_level: str = "info"
    title: str = "Scraping Platform API"
    description: str = "Distributed web scraping platform"
    version: str = "1.0.0"
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"
    
    # Pagination
    default_page_size: int = 50
    max_page_size: int = 1000
    
    # Request limits
    max_batch_size: int = 10000
    max_url_length: int = 2048
    
    # API keys for service-to-service communication
    internal_api_keys: List[str] = Field(default_factory=list)


# Default configuration
api_config = APIConfig()
