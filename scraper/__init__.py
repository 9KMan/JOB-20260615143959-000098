# =============================================================================
# Scraper Framework Package
# =============================================================================

__version__ = "1.0.0"
__author__ = "Scraper Team"

from scraper.config import settings
from scraper.database import init_db, close_db
from scraper.rabbitmq import init_rabbitmq, close_rabbitmq

__all__ = [
    "settings",
    "init_db",
    "close_db",
    "init_rabbitmq",
    "close_rabbitmq",
]
