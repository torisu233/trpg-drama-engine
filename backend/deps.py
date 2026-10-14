"""Shared dependencies: a lazily created LLM client (one instance shared by the whole app)."""
from typing import Optional
from .llm_client import LLMClient

_llm: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


async def close_llm() -> None:
    global _llm
    if _llm is not None:
        await _llm.close()
        _llm = None
