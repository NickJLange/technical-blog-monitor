"""
LLM generation module.
"""
from monitor.config import LLMConfig, LLMProvider
from monitor.llm.base import GenerationClient
from monitor.llm.openai import OpenAIGenerationClient
from monitor.llm.ollama import OllamaGenerationClient

def get_generation_client(config: LLMConfig) -> GenerationClient:
    """Factory to get the appropriate generation client."""
    if config.provider == LLMProvider.OPENAI:
        return OpenAIGenerationClient(config)
    elif config.provider == LLMProvider.OLLAMA:
        return OllamaGenerationClient(config)
    elif config.provider == LLMProvider.CUSTOM:
        # Fallback to Ollama or a dummy for now
        return OllamaGenerationClient(config)
    else:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")

__all__ = ["GenerationClient", "OpenAIGenerationClient", "OllamaGenerationClient", "get_generation_client"]
