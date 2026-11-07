"""Request schemas. ChatRequest/Message follow the Tech Guide so its React hook works unchanged."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = ""
    image: Optional[Dict[str, Any]] = None  # {"format": "png", "data": "<base64>"}
    audio: Optional[Dict[str, Any]] = None
    pdf: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    """Same fields as the guide. `use_mcp` turns on our local data tools."""

    model_id: Optional[str] = None
    chat_history: List[Message]
    use_mcp: bool = True
    approved_tool_calls: Optional[List[dict]] = []
    mcp_auto_approve: bool = True  # our tools are read-only, so they always auto-run


class DayContext(BaseModel):
    """What the manager knows about the target day that the calendar may not."""

    weather: Optional[Literal["clear", "rain", "drizzle", "hot"]] = None
    high_temp_f: Optional[float] = None
    holiday: Optional[str] = None
    local_event: Optional[str] = Field(None, examples=["Pro football home game"])
    university_in_session: Optional[bool] = None


class RecommendRequest(BaseModel):
    location: Literal["craig", "strip"]
    date: str = Field(..., examples=["2026-10-25"], description="YYYY-MM-DD")
    context: Optional[DayContext] = None
    on_hand: Dict[str, float] = Field(default_factory=dict, description="component_id -> qty")
    model_id: Optional[str] = None
    use_agent: bool = True
