"""
Base classes and interfaces for LLM generation.
"""
from typing import Protocol, Optional

class GenerationClient(Protocol):
    """Protocol defining the interface for LLM generation clients."""

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate text based on a prompt.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to guide behavior.

        Returns:
            str: The generated text.
        """
        ...

    async def close(self) -> None:
        """Close the client and release resources."""
        ...

    async def __aenter__(self) -> "GenerationClient":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager."""
        await self.close()
