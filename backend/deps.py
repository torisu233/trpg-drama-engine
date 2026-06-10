"""共用依賴：惰性建立的 Grok client（整個 app 共用一個）。"""
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
