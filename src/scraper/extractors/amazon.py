# src/scraper/extractors/amazon.py
"""Amazon product page extractor."""

import json
import re
from typing import Any, Dict

from src.scraper.scraper import BaseScraper, ExtractionResult, JobInput
from src.scraper.page import PageHelper


class AmazonExtractor(BaseScraper):
    """Scraper for Amazon product pages."""
    
    site_name = "amazon"
    
    async def extract(
        self,
        page: Any,
        page_helper: PageHelper,
        job: JobInput,
    ) -> ExtractionResult:
        """Extract product data from Amazon page."""
        result = ExtractionResult(
            url=job.url,
            status=ScraperStatus.SUCCESS,
        )
        
        try:
            # Extract product title
            title = await self._extract_title(page)
            if title:
                result.data["title"] = title
            
            # Extract price
            price = await self._extract_price(page)
            if price:
                result.data["price"] = price
            
            # Extract rating
            rating = await self._extract_rating(page)
            if rating:
                result.data["rating"] = rating
            
            # Extract reviews count
            reviews = await self._extract_reviews_count(page)
            if reviews:
                result.data["reviews_count"] = reviews
            
            # Extract availability
            availability = await self._extract_availability(page)
            if availability:
                result.data["availability"] = availability
            
            # Extract description
            description = await self._extract_description(page)
            if description:
                result.data["description"] = description
            
            # Extract ASIN
            asin = await self._extract_asin(job.url)
            if asin:
                result.data["asin"] = asin
            
            # Extract seller info
            seller = await self._extract_seller(page)
            if seller:
                result.data["seller"] = seller
            
        except Exception as e:
            result.add_error(f"Extraction error: {e}")
            result.status = ScraperStatus.PARTIAL
        
        return result
    
    async def _extract_title(self, page: Any) -> str:
        """Extract product title."""
        selectors = [
            "#productTitle",
            "#title",
            "h1.product-title-word-break",
            "[data-automation='product-title']",
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        
        return ""
    
    async def _extract_price(self, page: Any) -> Dict[str, str]:
        """Extract product price."""
        selectors = [
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#priceblock_saleprice",
            ".a-price .a-offscreen",
            "#corePrice_feature_div .a-offscreen",
            "[data-automation='product-price']",
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    # Clean price string
                    price_match = re.search(r"[\$£€]?[\d,]+\.?\d*", text)
                    if price_match:
                        return {
                            "value": price_match.group().replace(",", ""),
                            "raw": text.strip(),
                        }
            except Exception:
                continue
        
        return {"value": "", "raw": ""}
    
    async def _extract_rating(self, page: Any) -> float:
        """Extract star rating."""
        selectors = [
            "#acrPopover .a-icon-alt",
            "[data-automation='product-rating'] span",
            ".a-icon-star .a-icon-alt",
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    rating_match = re.search(r"(\d+\.?\d*)", text)
                    if rating_match:
                        return float(rating_match.group(1))
            except Exception:
                continue
        
        return 0.0
    
    async def _extract_reviews_count(self, page: Any) -> int:
        """Extract reviews count."""
        selectors = [
            "#acrCustomerReviewText",
            "[data-automation='product-review-count']",
            "#cmrs .a-section",
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    count_match = re.search(r"([\d,]+)", text)
                    if count_match:
                        return int(count_match.group(1).replace(",", ""))
            except Exception:
                continue
        
        return 0
    
    async def _extract_availability(self, page: Any) -> str:
        """Extract availability status."""
        selectors = [
            "#availability span",
            "#availability .a-color-success",
            "[data-automation='product-availability']",
            ".a-section.availability",
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        
        return "Unknown"
    
    async def _extract_description(self, page: Any) -> str:
        """Extract product description."""
        selectors = [
            "#productDescription p",
            "#feature-bullets li",
            "#productDescription",
            "[data-automation='product-description']",
        ]
        
        parts = []
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    text = await element.inner_text()
                    if text and text.strip():
                        parts.append(text.strip())
            except Exception:
                continue
        
        return "\n".join(parts[:5])  # Limit to first 5 items
    
    def _extract_asin(self, url: str) -> str:
        """Extract ASIN from URL."""
        asin_match = re.search(r"/dp/([A-Z0-9]{10})", url)
        if asin_match:
            return asin_match.group(1)
        
        asin_match = re.search(r"/gp/product/([A-Z0-9]{10})", url)
        if asin_match:
            return asin_match.group(1)
        
        return ""
    
    async def _extract_seller(self, page: Any) -> str:
        """Extract seller information."""
        selectors = [
            "#sellerProfileWidgetId a",
            "#merchant-sponsored-product",
            "[data-automation='product-seller']",
        ]
        
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        
        return "Amazon"
