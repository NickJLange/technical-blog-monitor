"""
OpenAI generation client.
"""
import structlog
from typing import Optional

from monitor.config import LLMConfig
from monitor.llm.base import GenerationClient

logger = structlog.get_logger()

class OpenAIGenerationClient(GenerationClient):
    """Async generation client for OpenAI."""

    def __init__(self, config: LLMConfig):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package is required for OpenAIGenerationClient")

        self.client = AsyncOpenAI(api_key=config.api_key.get_secret_value())
        self.model = config.model_name
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
        
        logger.info("OpenAI generation client initialized", model=self.model)

    async def close(self) -> None:
        await self.client.close()

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("OpenAI generation failed", error=str(e))
            raise
