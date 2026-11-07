"""
Tools the LLM can call.

The Tech Guide wires tools in through MCP servers. Our tools are local Python
functions over the order data, so we skip the MCP client and hand the model the
same OpenAI-style tool definitions directly. The loop is the guide's:
the model asks for a tool -> we run it -> append the result -> the model continues.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from services.data_service import DAYPART_NAMES, get_store


def _fn(name: str, description: str, properties: Dict[str, Any], required: list) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


LOCATION = {"type": "string", "enum": ["craig", "strip"], "description": "Store location key"}
DATE = {"type": "string", "description": "YYYY-MM-DD"}
MULTS = {
    "type": "object",
    "description": "Map of name -> multiplier between 0.5 and 2.0 (1.0 = no change)",
    "additionalProperties": {"type": "number"},
}

TOOL_DEFINITIONS = [
    _fn(
        "get_day_context",
        "Weather, holiday, university session and local event for a date. Fields are null when "
        "the date is outside the calendar. Includes anything the manager entered for the target date.",
        {"date": DATE},
        ["date"],
    ),
    _fn(
        "get_baseline",
        "Historical baseline for a location and target date: average of the last 8 same weekdays "
        "with holidays and events excluded. Returns daily and per-daypart order counts, delivery "
        "share, top items per daypart, and the weather/university status of each baseline day.",
        {"location": LOCATION, "date": DATE},
        ["location", "date"],
    ),
    _fn(
        "find_similar_days",
        "Past days before `before_date` that match the filters, each compared with its own baseline "
        "(ratio_vs_baseline, plus per daypart). Use it to measure how an event, holiday, weather "
        "type or university session changes demand. Text filters match by substring.",
        {
            "location": LOCATION,
            "before_date": DATE,
            "holiday": {"type": "string", "description": "e.g. 'Labor Day', 'Halloween'"},
            "local_event": {"type": "string", "description": "e.g. 'football', 'festival', 'move-in', 'fall break'"},
            "weather": {"type": "string", "enum": ["clear", "rain", "drizzle", "hot"]},
            "university_in_session": {"type": "boolean"},
            "weekday": {"type": "string", "description": "e.g. 'Sunday'"},
            "limit": {"type": "integer", "description": "Max days to return (default 6)"},
        },
        ["location", "before_date"],
    ),
    _fn(
        "get_stockout_history",
        "Prep components that ran out on recent same weekdays, with the time and unmet quantity. "
        "Sales on those days understate real demand.",
        {"location": LOCATION, "date": DATE, "weeks": {"type": "integer", "description": "default 8"}},
        ["location", "date"],
    ),
    _fn(
        "preview_prep_plan",
        "Compute ingredient totals for candidate multipliers so you can sanity-check them. "
        f"daypart_multipliers keys: {', '.join(DAYPART_NAMES)}. "
        "component_multipliers keys: component ids such as C01.",
        {
            "location": LOCATION,
            "date": DATE,
            "daypart_multipliers": MULTS,
            "component_multipliers": MULTS,
        },
        ["location", "date"],
    ),
]


class ToolContext:
    """Per-request state: manager-entered context for the target date."""

    def __init__(self, target_date: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None):
        self.target_date = target_date
        self.overrides = overrides or {}


def execute_tool(name: str, args: Dict[str, Any], ctx: Optional[ToolContext] = None) -> Dict[str, Any]:
    """Run one tool. Errors are returned to the model as data, not raised."""
    ctx = ctx or ToolContext()
    store = get_store()
    try:
        if "location" in args and args["location"] not in store.location_keys:
            return {"error": f"Unknown location {args['location']!r}. Use one of {store.location_keys}."}
        if name == "get_day_context":
            overrides = ctx.overrides if args["date"] == ctx.target_date else None
            return store.get_context(args["date"], overrides)
        if name == "get_baseline":
            return store.baseline_summary(args["location"], args["date"])
        if name == "find_similar_days":
            return store.find_similar_days(
                args["location"],
                args["before_date"],
                holiday=args.get("holiday"),
                local_event=args.get("local_event"),
                weather=args.get("weather"),
                university_in_session=args.get("university_in_session"),
                weekday=args.get("weekday"),
                limit=int(args.get("limit") or 6),
            )
        if name == "get_stockout_history":
            return store.stockout_history(args["location"], args["date"], int(args.get("weeks") or 8))
        if name == "preview_prep_plan":
            plan = store.prep_plan(
                args["location"],
                args["date"],
                args.get("daypart_multipliers"),
                args.get("component_multipliers"),
            )
            return {
                "daypart_multipliers_used": plan["daypart_multipliers"],
                "components": [
                    {
                        "id": r["component_id"],
                        "ingredient": r["ingredient"],
                        "baseline_need": r["baseline_need"],
                        "need": r["need"],
                        "unit": r["unit"],
                        "batches": r["batches"],
                    }
                    for r in plan["prep_sheet"]
                ],
            }
        return {"error": f"Unknown tool {name!r}"}
    except Exception as e:  # surface to the model so it can recover
        return {"error": f"{type(e).__name__}: {e}"}


def parse_tool_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
