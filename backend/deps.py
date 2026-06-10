"""共用依赖：惰性创建的 Grok client（整个 app 共用一个）。"""
from typing import Optional
from .grok_client import GrokClient

_grok: Optional[GrokClient] = None


def get_grok() -> GrokClient:
    global _grok
    if _grok is None:
        _grok = GrokClient()
    return _grok


async def close_grok() -> None:
    global _grok
    if _grok is not None:
        await _grok.close()
        _grok = None
