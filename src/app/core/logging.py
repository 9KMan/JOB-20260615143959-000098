# src/app/core/logging.py
"""
Logging Configuration.
Structured JSON logging for production, pretty console for development.
"""
import logging
import sys
from typing import Any

from pythonjsonlogger import jsonlogger

from app.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""
    
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["environment"] = settings.ENVIRONMENT
        if not record.name.startswith("app"):
            log_record["service"] = "scraping-fleet"


def setup_logging() -> None:
    """Configure logging based on environment."""
    root_logger = logging.getLogger()
    
    if settings.DEBUG:
        # Development: Pretty console output
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.setLevel(logging.DEBUG)
    else:
        # Production: JSON structured logging
        handler = logging.StreamHandler(sys.stdout)
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s"
        )
        handler.setFormatter(formatter)
        root_logger.setLevel(logging.INFO)
    
    root_logger.addHandler(handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
