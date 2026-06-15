# src/services/llm_classifier.py
"""
LLM-based error classification service.
"""
import json
import logging
from typing import Any, Dict, Optional

from src.config import config

logger = logging.getLogger(__name__)


class LLMErrorClassifier:
    """
    Uses LLM to classify scraping errors and determine appropriate actions.
    
    Classification categories:
    - TRANSIENT: Network issues, temporary blocks, rate limits (retry recommended)
    - TERMINAL: Permanent blocks, site structure changes (do not retry)
    - PROXY: Proxy-specific errors (may recover with different exit)
    - ANTI_BOT: Detection triggers (requires stealth fixes)
    - INFRA: Infrastructure issues (may recover)
    """
    
    def __init__(self):
        self.api_key = config.llm.api_key
        self.model = config.llm.model
        self.temperature = config.llm.temperature
        self.provider = config.llm.provider
    
    def is_available(self) -> bool:
        """Check if LLM classifier is configured and available."""
        return bool(self.api_key)
    
    async def classify_error(
        self,
        error: str,
        url: str,
        site: str
    ) -> "ErrorClassification":
        """
        Classify an error using LLM.
        
        Args:
            error: The error message or details
            url: The URL that was being scraped
            site: The site identifier
            
        Returns:
            ErrorClassification with category and recommendations
        """
        if not self.is_available():
            return self._default_classification(error)
        
        prompt = config.llm.error_classification_prompt.format(
            error_details=json.dumps({
                "error": error,
                "url": url,
                "site": site
            }),
            site_context=f"Target site: {site}"
        )
        
        try:
            response = await self._call_llm(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return self._default_classification(error)
    
    async def _call_llm(self, prompt: str) -> str:
        """Call LLM API."""
        if self.provider == "openai":
            return await self._call_openai(prompt)
        elif self.provider == "anthropic":
            return await self._call_anthropic(prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")
    
    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        import aiohttp
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a web scraping expert that classifies errors."},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": config.llm.max_tokens,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    raise Exception(f"OpenAI API error: {response.status}")
                
                data = await response.json()
                return data["choices"][0]["message"]["content"]
    
    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API."""
        import aiohttp
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": config.llm.max_tokens,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    raise Exception(f"Anthropic API error: {response.status}")
                
                data = await response.json()
                return data["content"][0]["text"]
    
    def _parse_response(self, response: str) -> "ErrorClassification":
        """Parse LLM response into ErrorClassification."""
        try:
            # Try to extract JSON from response
            data = json.loads(response)
            
            return ErrorClassification(
                category=data.get("classification", "unknown").lower(),
                error_code=data.get("classification", "UNKNOWN"),
                is_permanent=data.get("classification") in ["TERMINAL"],
                reasoning=data.get("reasoning", ""),
                recommended_action=data.get("recommended_action", "")
            )
        except json.JSONDecodeError:
            # Try to extract from text
            response_lower = response.lower()
            
            if "terminal" in response_lower:
                category = "terminal"
                is_permanent = True
            elif "proxy" in response_lower:
                category = "proxy"
                is_permanent = False
            elif "anti_bot" in response_lower or "anti-bot" in response_lower:
                category = "anti_bot"
                is_permanent = False
            elif "transient" in response_lower:
                category = "transient"
                is_permanent = False
            else:
                category = "unknown"
                is_permanent = False
            
            return ErrorClassification(
                category=category,
                error_code=category.upper(),
                is_permanent=is_permanent,
                reasoning=response[:500],
                recommended_action=""
            )
    
    def _default_classification(self, error: str) -> "ErrorClassification":
        """Return default classification based on error patterns."""
        error_lower = error.lower()
        
        if "tunnel" in error_lower:
            return ErrorClassification(
                category="proxy",
                error_code="ERR_TUNNEL",
                is_permanent=False,
                reasoning="Proxy tunnel error, may recover with different exit node"
            )
        elif "timeout" in error_lower:
            return ErrorClassification(
                category="transient",
                error_code="TIMEOUT",
                is_permanent=False,
                reasoning="Timeout error, may recover with retry"
            )
        elif any(x in error_lower for x in ["captcha", "blocked", "forbidden", "403", "429"]):
            return ErrorClassification(
                category="anti_bot",
                error_code="ANTI_BOT",
                is_permanent=False,
                reasoning="Anti-bot detection, requires stealth improvements"
            )
        elif any(x in error_lower for x in ["ssl", "certificate", "dns", "404", "not found"]):
            return ErrorClassification(
                category="terminal",
                error_code="TERMINAL_ERROR",
                is_permanent=True,
                reasoning="Terminal error, no point retrying"
            )
        else:
            return ErrorClassification(
                category="unknown",
                error_code="UNKNOWN",
                is_permanent=False,
                reasoning="Unknown error, treating as transient"
            )


@dataclass
class ErrorClassification:
    """Result of error classification."""
    category: str
    error_code: str
    is_permanent: bool
    reasoning: str
    recommended_action: str = ""
