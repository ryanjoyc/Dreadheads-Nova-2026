"""
Dreadheads NOVA 2026 backend.

Run:  uvicorn main:app --reload --port 8000   (from the backend/ folder)
Docs: http://localhost:8000/docs
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest, RecommendRequest
from services.agent import recommend
from services.chat_service import ChatService
from services.data_service import get_store
from services.openrouter import DEFAULT_MODEL, api_key

app = FastAPI(title="Dreadheads prep agent", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Agent runs cost credits and take several seconds, so cache by request.
_cache: Dict[str, Dict[str, Any]] = {}


@app.on_event("startup")
def _load_data() -> None:
    get_store()


def _validate_date(d: str) -> None:
    from datetime import date

    try:
        date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")


async def _recommendation(req: RecommendRequest, refresh: bool = False) -> Dict[str, Any]:
    _validate_date(req.date)
    key = json.dumps(req.model_dump(), sort_keys=True)
    if refresh or key not in _cache:
        _cache[key] = await recommend(
            req.location,
            req.date,
            overrides=req.context.model_dump() if req.context else None,
            on_hand=req.on_hand,
            model=req.model_id,
            use_agent=req.use_agent,
        )
    return _cache[key]


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "api_key_set": bool(api_key()), "default_model": DEFAULT_MODEL}


@app.get("/meta")
def meta() -> Dict[str, Any]:
    return get_store().meta()


@app.post("/recommendations")
async def recommendations(req: RecommendRequest, refresh: bool = False) -> Dict[str, Any]:
    """Prep sheet + timeline + flags + agent trace (+ backtest when the date is in history)."""
    return await _recommendation(req, refresh)


@app.get("/prep-sheet")
async def prep_sheet(
    date: str,
    location: str = Query("strip", pattern="^(craig|strip)$"),
    local_event: Optional[str] = None,
    weather: Optional[str] = None,
    use_agent: bool = True,
) -> Dict[str, Any]:
    ctx = {"local_event": local_event, "weather": weather} if (local_event or weather) else None
    res = await _recommendation(
        RecommendRequest(location=location, date=date, context=ctx, use_agent=use_agent)
    )
    keys = ["data_label", "location", "date", "summary", "flags", "prep_sheet", "caveat", "agent"]
    return {k: res[k] for k in keys}


@app.get("/timeline")
async def timeline(
    date: str,
    location: str = Query("strip", pattern="^(craig|strip)$"),
    local_event: Optional[str] = None,
    weather: Optional[str] = None,
    use_agent: bool = True,
) -> Dict[str, Any]:
    ctx = {"local_event": local_event, "weather": weather} if (local_event or weather) else None
    res = await _recommendation(
        RecommendRequest(location=location, date=date, context=ctx, use_agent=use_agent)
    )
    return {k: res[k] for k in ["data_label", "location", "date", "open", "close", "timeline"]}


@app.get("/heatmap")
def heatmap(
    location: str = Query("strip", pattern="^(craig|strip)$"),
    metric: str = Query("orders", description="'orders' or a menu item id like M10"),
    channel: str = Query("all", pattern="^(all|doordash|grubhub)$"),
    end_date: Optional[str] = None,
    weeks: int = 8,
    include_special: bool = False,
) -> Dict[str, Any]:
    if end_date:
        _validate_date(end_date)
    return get_store().heatmap(location, metric, channel, end_date, weeks, include_special)


@app.post("/chat_streaming")
async def chat_streaming(request: ChatRequest):
    """Free-form chat about the data, streamed as NDJSON (see services/chat_service.py)."""
    service = ChatService(request.model_id)
    payload = service.create_payload(service.prepare_messages(request.chat_history), request.use_mcp)

    async def event_generator():
        async for event in service.stream_response(payload, use_tools=request.use_mcp):
            yield event

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
