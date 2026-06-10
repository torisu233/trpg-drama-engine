"""Grok 客户端：openai SDK（指向 x.ai）+ instructor。

instructor 的 max_retries 提供「结构化输出验证失败时自动把错误回馈给模型重问」的保险，
让四个 agent 的 JSON 输出更稳。对外维持与旧版相同的 call() 接口，上层程序无需改动。
"""
import os
import logging
from typing import Type, TypeVar
from pydantic import BaseModel
from openai import AsyncOpenAI
import instructor

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GrokError(Exception):
    pass


class GrokClient:
    def __init__(self, timeout: float = 60.0, max_retries: int = 3):
        api_key = os.getenv("GROK_API_KEY")
        base_url = os.getenv("GROK_API_BASE_URL", "https://api.x.ai/v1")
        if not api_key:
            raise ValueError("GROK_API_KEY 未设置，请在 .env 配置")
        # x.ai 与 OpenAI API 兼容
        self._raw = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        # JSON 模式：强制 json_object 输出 + Pydantic 验证；失败自动重问
        self.client = instructor.from_openai(self._raw, mode=instructor.Mode.JSON)
        self.max_retries = max_retries
        self.model_default = os.getenv("GROK_MODEL", "grok-3")

    async def call(
        self,
        prompt: str,
        schema: Type[T],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: str = "",
    ) -> T:
        """调用 Grok，回传经 Pydantic 验证的结构化对象；验证失败会自动重问。"""
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
            logger.error(f"[Grok] {schema.__name__} 调用/验证失败: {e}")
            raise GrokError(f"Grok 调用/验证失败（{schema.__name__}）: {e}") from e

    async def close(self):
        await self._raw.close()
