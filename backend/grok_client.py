"""Grok 客戶端：openai SDK（指向 x.ai）+ instructor。

instructor 的 max_retries 提供「結構化輸出驗證失敗時自動把錯誤回饋給模型重問」的保險，
讓四個 agent 的 JSON 輸出更穩。對外維持與舊版相同的 call() 介面，上層程式無需改動。
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
            raise ValueError("GROK_API_KEY 未設定，請在 .env 配置")
        # x.ai 與 OpenAI API 相容
        self._raw = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        # JSON 模式：強制 json_object 輸出 + Pydantic 驗證；失敗自動重問
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
        """呼叫 Grok，回傳經 Pydantic 驗證的結構化物件；驗證失敗會自動重問。"""
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
            logger.error(f"[Grok] {schema.__name__} 呼叫/驗證失敗: {e}")
            raise GrokError(f"Grok 呼叫/驗證失敗（{schema.__name__}）: {e}") from e

    async def close(self):
        await self._raw.close()
