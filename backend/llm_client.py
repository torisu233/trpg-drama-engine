"""LLM client: openai SDK (any OpenAI-compatible endpoint, currently DeepSeek) + instructor.

instructor's max_retries adds a safety net: when structured output fails validation, the error is
fed back to the model and it is asked again. This keeps the four agents' JSON output stable (and also
covers DeepSeek JSON mode occasionally returning empty content). The public call() interface is unchanged.
env: LLM_API_KEY / LLM_API_BASE_URL / LLM_MODEL (values point at DeepSeek).
"""
import os
import logging
from typing import Type, TypeVar
from pydantic import BaseModel
from openai import AsyncOpenAI
import instructor

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, timeout: float = 60.0, max_retries: int = 3):
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_API_BASE_URL", "https://api.deepseek.com")
        if not api_key:
            raise ValueError("LLM_API_KEY is not set; configure it in .env")
        # DeepSeek is OpenAI API compatible
        self._raw = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        # JSON mode: force json_object output + Pydantic validation; re-ask automatically on failure
        self.client = instructor.from_openai(self._raw, mode=instructor.Mode.JSON)
        self.max_retries = max_retries
        self.model_default = os.getenv("LLM_MODEL", "deepseek-chat")

    async def call(
        self,
        prompt: str,
        schema: Type[T],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: str = "",
    ) -> T:
        """Call the LLM and return a Pydantic-validated structured object; re-asks automatically on validation failure."""
        try:
            return await self.client.chat.completions.create(
                model=model or self.model_default,
                messages=[{"role": "user", "content": prompt}],
                response_model=schema,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=self.max_retries,
            )
        except Exception as e:
            logger.error(f"[LLM] {schema.__name__} call/validation failed: {e}")
            raise LLMError(f"LLM call/validation failed ({schema.__name__}): {e}") from e

    async def close(self):
        await self._raw.close()
