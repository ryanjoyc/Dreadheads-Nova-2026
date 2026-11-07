"""
Streaming chat with tool calls, following the Tech Guide's ChatService.

Differences from the guide's sample:
- httpx.AsyncClient instead of blocking `requests` inside async code.
- Tools are our local data functions (services/tools.py), not MCP servers.
- The guide's missing helpers (_accumulate_tool_calls, _execute_tools) are implemented.
- Output is NDJSON: one JSON object per line. Lines are either raw OpenRouter
  chunks (read choices[0].delta.content) or our own {"type": "tool_call" | "error", ...}.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from models.schemas import Message
from services.data_service import get_store
from services.openrouter import DEFAULT_MODEL, OPENROUTER_URL, api_key, headers
from services.tools import TOOL_DEFINITIONS, execute_tool, parse_tool_args

MAX_TOOL_DEPTH = 6


def chat_system_prompt() -> str:
    store = get_store()
    return (
        "You help a restaurant manager at Steel City Bowls (a fictional restaurant; all data is SYNTHETIC) "
        "understand order history and plan prep. Locations: craig (student-heavy) and strip (office and "
        f"game-day crowds). Order data covers {store.first_date} to {store.last_date}. "
        "Use the tools for every number you state; never estimate numbers yourself. "
        "Keep answers short and practical."
    )


class ChatService:
    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id or DEFAULT_MODEL

    def prepare_messages(self, chat_history: List[Message]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": chat_system_prompt()}]
        for msg in chat_history:
            content: List[Dict[str, Any]] = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})
            if msg.image:
                url = f"data:image/{msg.image['format']};base64,{msg.image['data']}"
                content.append({"type": "image_url", "image_url": {"url": url}})
            messages.append({"role": msg.role, "content": content})
        return messages

    def create_payload(self, messages: List[Dict[str, Any]], use_tools: bool) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": self.model_id, "messages": messages, "stream": True}
        if use_tools:
            payload["tools"] = TOOL_DEFINITIONS
        return payload

    @staticmethod
    def _accumulate_tool_calls(deltas: List[Dict[str, Any]], acc: Dict[int, Dict[str, Any]]) -> None:
        """Tool calls stream in pieces; stitch them together by index."""
        for d in deltas:
            slot = acc.setdefault(
                d.get("index", 0), {"id": None, "type": "function", "function": {"name": "", "arguments": ""}}
            )
            if d.get("id"):
                slot["id"] = d["id"]
            fn = d.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] += fn["name"]
            if fn.get("arguments"):
                slot["function"]["arguments"] += fn["arguments"]

    async def stream_response(self, payload: Dict[str, Any], use_tools: bool, depth: int = 0) -> AsyncGenerator[str, None]:
        if not api_key():
            yield json.dumps({"type": "error", "error": "No API key: set OPENROUTER_KEY in backend/.env"}) + "\n"
            return

        content = ""
        tool_acc: Dict[int, Dict[str, Any]] = {}
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", OPENROUTER_URL, headers=headers(), json=payload) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode(errors="replace")[:300]
                    yield json.dumps({"type": "error", "error": f"OpenRouter {r.status_code}: {body}"}) + "\n"
                    return
                buffer = ""
                async for text in r.aiter_text():
                    buffer += text
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line.startswith("data: "):
                            continue  # SSE comments like ": OPENROUTER PROCESSING"
                        data = line[6:]
                        if data == "[DONE]":
                            continue
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = parsed.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            content += delta.get("content") or ""
                            if delta.get("tool_calls"):
                                self._accumulate_tool_calls(delta["tool_calls"], tool_acc)
                        yield data + "\n"

        if not (use_tools and tool_acc) or depth >= MAX_TOOL_DEPTH:
            return

        calls = [tool_acc[i] for i in sorted(tool_acc)]
        payload["messages"].append({"role": "assistant", "content": content, "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            args = parse_tool_args(call["function"]["arguments"])
            result = execute_tool(name, args)
            yield json.dumps({"type": "tool_call", "name": name, "args": args, "ok": "error" not in result}) + "\n"
            payload["messages"].append(
                {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, default=str)}
            )
        async for event in self.stream_response(payload, use_tools, depth + 1):
            yield event
