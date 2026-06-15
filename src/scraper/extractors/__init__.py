# src/scraper/extractors/__init__.py
"""Site-specific data extractors."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from src.scraper.scraper import BaseScraper, ExtractionResult, JobInput
from src.scraper.page import PageHelper


class BaseExtractor(ABC):
    """Base class for site-specific data extractors."""
    
    @abstractmethod
    async def extract(
        self,
        page: Any,
        page_helper: PageHelper,
        job: JobInput,
    ) -> Dict[str, Any]:
        """Extract structured data from page.
        
        Args:
            page: Playwright page
            page_helper: Page helper instance
            job: Job input
            
        Returns:
            Extracted data dictionary
        """
        pass
