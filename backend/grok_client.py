"""Grok API 客戶端（對齊 x.ai，強制 JSON + Pydantic 驗證）。"""
from typing import Optional, Type, TypeVar
from pydantic import BaseModel
import httpx
import json
import os
import logging

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GrokError(Exception):
    pass


class GrokClient:
    def __init__(self, timeout: float = 60.0, max_retries: int = 2):
        self.api_key = os.getenv("GROK_API_KEY")
        self.base_url = os.getenv("GROK_API_BASE_URL", "https://api.x.ai/v1")
        self.max_retries = max_retries
        if not self.api_key:
            raise ValueError("GROK_API_KEY 未設定，請在 .env 配置")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def call(
        self,
        prompt: str,
        schema: Type[T],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: str = "",
    ) -> T:
        """呼叫 Grok，回傳經 Pydantic 驗證的結構化物件。"""
        model = model or os.getenv("GROK_MODEL", "grok-3")
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        attempt = 0
        last = None
        while attempt <= self.max_retries:
            try:
                resp = await self.client.post(f"{self.base_url}/chat/completions", json=body)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return schema(**parsed)
            except httpx.HTTPStatusError as e:
                last = GrokError(f"HTTP {e.response.status_code}: {e.response.text[:300]}")
                if e.response.status_code >= 500 and attempt < self.max_retries:
                    attempt += 1
                    continue
                raise last
            except (json.JSONDecodeError, KeyError) as e:
                last = GrokError(f"回應解析失敗: {e}")
                if attempt < self.max_retries:
                    attempt += 1
                    continue
                raise last
            except Exception as e:
                last = GrokError(f"驗證/未知錯誤: {e}")
                if attempt < self.max_retries:
                    attempt += 1
                    continue
                raise last
        raise last or GrokError("呼叫失敗")

    async def close(self):
        await self.client.aclose()
