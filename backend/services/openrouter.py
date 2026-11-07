"""OpenRouter settings and a non-streaming call, following the Tech Guide."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")


def api_key() -> Optional[str]:
    # The guide's setup step writes OPENROUTER_KEY; its sample code reads OPENROUTER_API_KEY.
    return os.getenv("OPENROUTER_KEY") or os.getenv("OPENROUTER_API_KEY")


def headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
        "X-Title": "Dreadheads NOVA 2026",
    }


class OpenRouterError(RuntimeError):
    pass


async def chat_completion(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    temperature: float = 0.2,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    if not api_key():
        raise OpenRouterError("No API key: set OPENROUTER_KEY in backend/.env")
    payload: Dict[str, Any] = {"model": model or DEFAULT_MODEL, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(OPENROUTER_URL, headers=headers(), json=payload)
    if r.status_code != 200:
        raise OpenRouterError(f"OpenRouter {r.status_code}: {r.text[:300]}")
    data = r.json()
    if "error" in data:
        raise OpenRouterError(f"OpenRouter error: {data['error']}")
    return data
