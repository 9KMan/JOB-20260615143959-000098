# src/config/settings.py
"""
Environment variable validation and settings management.
"""
import os
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]


def validate_required_env_vars() -> ValidationResult:
    """Validate that all required environment variables are set."""
    errors = []
    warnings = []
    
    required = {
        "POSTGRES_PASSWORD": "Database password",
        "RABBITMQ_PASSWORD": "RabbitMQ password",
        "OXYLABS_USERNAME": "Oxylabs proxy username",
        "OXYLABS_PASSWORD": "Oxylabs proxy password",
        "LLM_API_KEY": "LLM API key",
    }
    
    for var, description in required.items():
        if not os.getenv(var):
            errors.append(f"Missing required environment variable: {var} ({description})")
    
    # Validate optional but recommended settings
    if not os.getenv("RABBITMQ_HOST"):
        warnings.append("RABBITMQ_HOST not set, using default 'localhost'")
    
    if not os.getenv("POSTGRES_HOST"):
        warnings.append("POSTGRES_HOST not set, using default 'localhost'")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def validate_proxy_config() -> ValidationResult:
    """Validate proxy configuration."""
    errors = []
    warnings = []
    
    username = os.getenv("OXYLABS_USERNAME")
    password = os.getenv("OXYLABS_PASSWORD")
    
    if username and password:
        if len(password) < 8:
            warnings.append("Oxylabs password seems too short")
    
    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def get_log_level(env_var: str = "LOG_LEVEL") -> int:
    """Get log level from environment variable."""
    level = os.getenv(env_var, "INFO").upper()
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return levels.get(level, logging.INFO)


def configure_logging() -> None:
    """Configure logging based on environment settings."""
    log_level = get_log_level()
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("pyppeteer").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pika").setLevel(logging.WARNING)


def validate_all() -> ValidationResult:
    """Run all configuration validations."""
    all_errors = []
    all_warnings = []
    
    # Run validations
    result = validate_required_env_vars()
    all_errors.extend(result.errors)
    all_warnings.extend(result.warnings)
    
    result = validate_proxy_config()
    all_errors.extend(result.errors)
    all_warnings.extend(result.warnings)
    
    # Log warnings
    for warning in all_warnings:
        logger.warning(f"Configuration warning: {warning}")
    
    # Raise error if critical issues found
    if all_errors:
        error_msg = "Configuration errors found:\n" + "\n".join(f"  - {e}" for e in all_errors)
        logger.error(error_msg)
    
    return ValidationResult(
        valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings
    )
