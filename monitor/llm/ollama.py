"""
Ollama generation client.
"""
import httpx
import structlog
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from monitor.config import LLMConfig
from monitor.llm.base import GenerationClient

logger = structlog.get_logger()

class OllamaGenerationClient(GenerationClient):
    """Async generation client for local Ollama instance."""

    def __init__(self, config: LLMConfig):
        self.base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        self.model = config.model_name
        self.timeout = config.timeout_seconds
        self._client = httpx.AsyncClient(timeout=self.timeout)
        
        logger.info(
            "Ollama generation client initialized",
            base_url=self.base_url,
            model=self.model
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        wait=wait_exponential(min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7  # Default, can be configurable if needed
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt

        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
            
        except Exception as e:
            logger.error("Ollama generation failed", error=str(e), model=self.model)
            raise
