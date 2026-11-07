"""OpenRouter agent that predicts a day's rush hours from order traffic.

Rule: plain Python does every calculation. `rush.forecast` averages traffic for the same
weekday and flags spike slots. The model investigates through read-only tools (all built on
the `/order-lines` and `/stores` query functions via `analytics`), then returns rush windows
with a multiplier between 0.5x and 2.0x and a reason for each. Python snaps the windows to
the slot grid, clamps the multipliers, and recomputes every number from the forecast.

Without a key, with `use_agent=false`, or if the model fails, the endpoint returns the plain
forecast's rush windows and adds a flag saying so.
"""

import json
import logging
import math
import re
from collections.abc import Callable
from datetime import date, time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from nova_backend import analytics, rush
from nova_backend.config import get_settings
from nova_backend.schemas import OrderScope, RushParams, TopDishParams

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TURNS = 8
MAX_TOOL_DAYS = 62
MIN_MULTIPLIER, MAX_MULTIPLIER = 0.5, 2.0

SYSTEM_PROMPT = """You predict rush hours (time frames of heavy order traffic) for a \
restaurant kitchen on one day, so staff can prepare before the spike arrives.

Use the tools before answering. Start with get_rush_forecast, which averages the same \
weekday over recent weeks and lists the slots that spike. Then check whether the pattern \
holds: look at individual recent days with get_day_traffic, and use count_orders or \
get_top_dishes when they help explain a rush. You can only see data from before the day \
being predicted.

Rules:
- Do not do arithmetic for the final numbers. Python recomputes expected orders from the \
forecast times your multiplier.
- multiplier scales the forecast for that window: 1.0 means as forecast. Use another value \
only with evidence, such as the manager's context (an event, weather) or a clear recent \
trend. Allowed range 0.5 to 2.0.
- Windows use 24-hour store-local "HH:MM" times on the slot grid and must not overlap.
- You may drop a forecast rush that recent days do not support, or add one the context \
implies; say why in the reason.
- Keep each reason to one or two sentences a kitchen manager can act on.

Reply with only this JSON:
{"rush_hours": [{"start": "HH:MM", "end": "HH:MM", "multiplier": 1.0, \
"confidence": "high|medium|low", "reason": "..."}], "summary": "...", "flags": ["..."]}"""


class AgentError(RuntimeError):
    """The model could not produce a usable answer."""


def _openrouter() -> tuple[str | None, str]:
    settings = get_settings()
    return settings.openrouter_key, settings.openrouter_model


def _chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]], model: str) -> dict:
    key, _ = _openrouter()
    try:
        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "X-Title": "Dreadheads NOVA 2026",
            },
            json={"model": model, "messages": messages, "tools": tools, "temperature": 0.2},
            timeout=90.0,
        )
    except httpx.HTTPError as exc:
        raise AgentError(f"OpenRouter request failed ({type(exc).__name__})") from exc
    if response.status_code != 200:
        raise AgentError(f"OpenRouter returned HTTP {response.status_code}")
    try:
        data = response.json()
        message = data["choices"][0]["message"]
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise AgentError("OpenRouter returned an invalid response") from exc
    if not isinstance(message, dict) or "error" in data:
        raise AgentError("OpenRouter returned an error")
    return message


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


DATE = {"type": "string", "description": "YYYY-MM-DD, before the day being predicted"}
CLOCK = {"type": "string", "description": "HH:MM store-local time of day"}
TOOLS = [
    _tool(
        "get_rush_forecast",
        "Forecast for the day being predicted: average orders per slot over the same "
        "weekday in recent weeks, the rush threshold, and the forecast rush windows.",
        {"weeks": {"type": "integer", "minimum": 1, "maximum": 26}},
        [],
    ),
    _tool(
        "get_day_traffic",
        "Actual orders per slot on one past day, and which slots spiked that day.",
        {"date": DATE},
        ["date"],
    ),
    _tool(
        "count_orders",
        "Count distinct orders in a past date range (end exclusive, at most 62 days), "
        "optionally within a time of day and containing a dish name.",
        {
            "date_start": DATE,
            "date_end": DATE,
            "time_start": CLOCK,
            "time_end": CLOCK,
            "item_name": {"type": "string"},
        },
        ["date_start", "date_end"],
    ),
    _tool(
        "get_top_dishes",
        "Most ordered dishes in a past date range (end exclusive, at most 62 days), "
        "optionally within a time of day.",
        {
            "date_start": DATE,
            "date_end": DATE,
            "time_start": CLOCK,
            "time_end": CLOCK,
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        ["date_start", "date_end"],
    ),
]


class Tools:
    """Read-only tools bound to one request's store scope and day."""

    def __init__(self, session: Session, params: RushParams, scope: OrderScope):
        self.session, self.params, self.scope = session, params, scope

    def _past_range(self, args: dict[str, Any]) -> tuple[date, date]:
        start = date.fromisoformat(args["date_start"])
        end = date.fromisoformat(args["date_end"])
        if not start < end <= self.params.on_date:
            raise ValueError("Need date_start < date_end <= the day being predicted")
        if (end - start).days > MAX_TOOL_DAYS:
            raise ValueError(f"Date range is limited to {MAX_TOOL_DAYS} days")
        return start, end

    def _clock(self, args: dict[str, Any], key: str) -> time | None:
        return time.fromisoformat(args[key]) if args.get(key) else None

    def get_rush_forecast(self, args: dict[str, Any]) -> dict[str, Any]:
        weeks = int(args.get("weeks") or self.params.weeks)
        if not 1 <= weeks <= 26:
            raise ValueError("weeks must be 1-26")
        fc = rush.forecast(
            self.session, self.scope, self.params.on_date, self.params.slot_minutes, weeks
        )
        return {
            "history_days": [d.isoformat() for d in fc.history],
            "typical_orders_per_slot": round(fc.typical, 2),
            "rush_threshold": round(fc.threshold, 2),
            "expected_by_slot": {rush.label(s): round(v, 2) for s, v in fc.expected.items()},
            "rush_windows": [fc.window_stats(s, e) for s, e in fc.rush_windows()],
        }

    def get_day_traffic(self, args: dict[str, Any]) -> dict[str, Any]:
        day = date.fromisoformat(args["date"])
        if day >= self.params.on_date:
            raise ValueError("Only days before the day being predicted are available")
        counts = rush.day_traffic(self.session, self.scope, day, self.params.slot_minutes)
        return {"date": day.isoformat(), "weekday": day.strftime("%A")} | rush.day_spikes(
            counts, self.params.slot_minutes
        )

    def count_orders(self, args: dict[str, Any]) -> dict[str, Any]:
        start, end = self._past_range(args)
        params = self.scope.model_copy(
            update={
                "date_start": start,
                "date_end": end,
                "time_start": self._clock(args, "time_start"),
                "time_end": self._clock(args, "time_end"),
            }
        )
        wanted = (args.get("item_name") or "").casefold()
        orders = {
            line["order_id"]
            for line, _ in analytics.scoped_lines(self.session, params)
            if wanted in line["item_name"].casefold()
        }
        return {"orders": len(orders), "days": (end - start).days}

    def get_top_dishes(self, args: dict[str, Any]) -> dict[str, Any]:
        start, end = self._past_range(args)
        params = TopDishParams(
            source=self.scope.source,
            store_id=self.scope.store_id,
            store_name=self.scope.store_name,
            date_start=start,
            date_end=end,
            time_start=self._clock(args, "time_start"),
            time_end=self._clock(args, "time_end"),
            limit=int(args.get("limit") or 5),
        )
        ranked = analytics.top_dishes(self.session, params)["data"]
        return {
            "dishes": [
                {"item_name": d["item_name"], "units": float(d["units"]), "orders": d["orders"]}
                for d in ranked
            ]
        }

    def run(self, name: str, raw_args: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "get_rush_forecast": self.get_rush_forecast,
            "get_day_traffic": self.get_day_traffic,
            "count_orders": self.count_orders,
            "get_top_dishes": self.get_top_dishes,
        }
        try:
            args = json.loads(raw_args or "{}")
            if not isinstance(args, dict):
                raise ValueError("Arguments must be a JSON object")
        except ValueError:
            return {}, {"error": "Arguments were not a JSON object"}
        if name not in handlers:
            return args, {"error": f"Unknown tool {name}"}
        try:
            return args, handlers[name](args)
        except (KeyError, TypeError, ValueError) as exc:
            return args, {"error": str(exc) or type(exc).__name__}


def _brief(result: dict[str, Any]) -> str:
    if "error" in result:
        return f"error: {result['error']}"
    if "rush_windows" in result:
        windows = ", ".join(f"{w['start']}-{w['end']}" for w in result["rush_windows"])
        return f"{len(result['history_days'])} history days; forecast rushes: {windows or 'none'}"
    if "spike_slots" in result:
        spikes = ", ".join(result["spike_slots"]) or "none"
        return f"{result['date']}: {result['total_orders']} orders; spikes at {spikes}"
    if "dishes" in result:
        return ", ".join(d["item_name"] for d in result["dishes"]) or "no dishes"
    if "orders" in result:
        return f"{result['orders']} orders over {result['days']} days"
    return json.dumps(result)[:200]


def _parse_json(content: str | None) -> dict[str, Any]:
    if not isinstance(content, str) or not content:
        raise AgentError("The model returned no text answer")
    match = re.search(r"\{.*\}", content, re.DOTALL)
    try:
        decision = json.loads(match.group(0) if match else content)
    except ValueError as exc:
        raise AgentError("The model's answer was not JSON") from exc
    if not isinstance(decision, dict) or not isinstance(decision.get("rush_hours"), list):
        raise AgentError("The model's answer had no rush_hours list")
    flags = decision.get("flags")
    if flags is not None and (
        not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags)
    ):
        raise AgentError("The model's flags must be a list of strings")
    return decision


ChatFn = Callable[[list[dict[str, Any]], list[dict[str, Any]], str], dict[str, Any]]


def run_agent(
    session: Session,
    params: RushParams,
    scope: OrderScope,
    model: str,
    chat: ChatFn,
    bound_tools: Tools | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tools = bound_tools if bound_tools is not None else Tools(session, params, scope)
    request = {
        "date": params.on_date.isoformat(),
        "weekday": params.on_date.strftime("%A"),
        "current_time": params.from_time.strftime("%H:%M"),
        "until": params.until.strftime("%H:%M") if params.until else None,
        "slot_minutes": params.slot_minutes,
        "store": scope.model_dump(mode="json", exclude_none=True, exclude={"on_date"}) or "all",
        "manager_context": params.context,
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Predict the rush hours for:\n" + json.dumps(request)},
    ]
    trace: list[dict[str, Any]] = []
    for _ in range(MAX_TURNS):
        message = chat(messages, TOOLS, model)
        if not isinstance(message, dict):
            raise AgentError("The model returned an invalid message")
        calls = message.get("tool_calls") or []
        if not isinstance(calls, list):
            raise AgentError("The model's tool_calls must be a list")
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if (
                not isinstance(function, dict)
                or not isinstance(call.get("id"), str)
                or not call["id"]
                or not isinstance(function.get("name"), str)
                or not isinstance(function.get("arguments", "{}"), (str, type(None)))
            ):
                raise AgentError("The model returned an invalid tool call")
        messages.append(
            {"role": "assistant", "content": message.get("content") or "", "tool_calls": calls}
            if calls
            else {"role": "assistant", "content": message.get("content") or ""}
        )
        if not calls:
            return _parse_json(message.get("content")), trace
        for call in calls:
            name = call.get("function", {}).get("name", "")
            args, result = tools.run(name, call.get("function", {}).get("arguments"))
            trace.append({"tool": name, "args": args, "result": _brief(result)})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, default=str),
                }
            )
    raise AgentError(f"No final answer after {MAX_TURNS} turns")


def _to_minute(value: Any, slot: int, round_up: bool) -> int:
    text = str(value).strip()
    if text == "24:00":
        return rush.DAY_MINUTES
    minute = rush.minute_of(time.fromisoformat(text))
    if round_up and minute % slot:
        return minute + slot - minute % slot
    return minute - minute % slot


def _normalize(
    decision: dict[str, Any], fc: rush.Forecast, flags: list[str]
) -> list[tuple[int, int, dict[str, Any]]]:
    """Snap agent windows to the grid, clamp multipliers, and recompute their numbers."""
    windows: list[tuple[int, int, dict[str, Any]]] = []
    for raw in decision["rush_hours"][:12]:
        if not isinstance(raw, dict):
            flags.append("ai_window_invalid: skipped a non-object rush window")
            continue
        try:
            start = _to_minute(raw["start"], fc.slot_minutes, round_up=False)
            end = min(_to_minute(raw["end"], fc.slot_minutes, round_up=True), rush.DAY_MINUTES)
            asked = float(raw.get("multiplier", 1.0))
        except (KeyError, TypeError, ValueError):
            flags.append("ai_window_invalid: skipped a rush window with bad times or numbers")
            continue
        if not math.isfinite(asked):
            flags.append("ai_window_invalid: skipped a non-finite multiplier")
            continue
        if start >= end:
            flags.append("ai_window_invalid: skipped a rush window that ends before it starts")
            continue
        if any(start < e and s < end for s, e, _ in windows):
            flags.append(f"ai_window_overlap: skipped {rush.label(start)}-{rush.label(end)}")
            continue
        multiplier = min(MAX_MULTIPLIER, max(MIN_MULTIPLIER, asked))
        stats = fc.window_stats(start, end, multiplier)
        if isinstance(raw.get("confidence"), str) and raw["confidence"] in {
            "high",
            "medium",
            "low",
        }:
            stats["confidence"] = raw["confidence"]
        stats |= {
            "multiplier": multiplier,
            "clamped_from": asked if multiplier != asked else None,
            "reason": str(raw.get("reason") or "")[:400],
        }
        windows.append((start, end, stats))
    return sorted(windows, key=lambda w: w[0])


def _baseline_reason(stats: dict[str, Any], fc: rush.Forecast) -> str:
    weekday = fc.day.strftime("%A")
    return (
        f"Recent {weekday}s peak at {stats['peak_at']} with about "
        f"{stats['expected_peak_orders']:g} orders per {fc.slot_minutes} minutes, "
        f"{stats['intensity']:g}x a typical slot; busy in {stats['busy_days']} of "
        f"{len(fc.history)} recent {weekday}s."
    )


def predict_rush_hours(
    session: Session,
    params: RushParams,
    chat: ChatFn | None = None,
    *,
    forecast: rush.Forecast | None = None,
    actual_traffic: dict | None = None,
    bound_tools: Tools | None = None,
) -> dict[str, Any]:
    """Forecast the day's traffic, then let the agent refine the rush windows if it can."""
    scope = params.scope()
    slot = params.slot_minutes
    fc = (
        forecast
        if forecast is not None
        else rush.forecast(session, scope, params.on_date, slot, params.weeks)
    )
    actual = (
        actual_traffic
        if actual_traffic is not None
        else rush.day_traffic(session, scope, params.on_date, slot)
    )
    flags: list[str] = []
    trace: list[dict[str, Any]] = []
    key, model = _openrouter()
    method, summary = "baseline", ""

    windows: list[tuple[int, int, dict[str, Any]]] = []
    if not fc.history:
        flags.append(
            f"no_history: no orders on the previous {params.weeks} {params.on_date:%A}s "
            "for this store scope, so there is nothing to forecast from"
        )
    if fc.history and params.use_agent and key:
        try:
            decision, trace = run_agent(session, params, scope, model, chat or _chat, bound_tools)
            windows = _normalize(decision, fc, flags)
            method = "agent"
            summary = str(decision.get("summary") or "")[:1000]
            flags.extend(str(f)[:300] for f in decision.get("flags") or [] if f)
        except AgentError as exc:
            logger.warning("Rush agent failed: %s", exc)
            flags.append(f"ai_unavailable: {exc}; showing the historical forecast")
    elif fc.history and params.use_agent:
        flags.append("ai_unavailable: OPENROUTER_KEY is not set; showing the historical forecast")
    if fc.history and method == "baseline":
        if params.context:
            flags.append("context_ignored: manager context needs the AI agent")
        for start, end in fc.rush_windows():
            stats = fc.window_stats(start, end)
            stats |= {"multiplier": 1.0, "clamped_from": None}
            stats["reason"] = _baseline_reason(stats, fc)
            windows.append((start, end, stats))

    now = rush.minute_of(params.from_time)
    until = rush.minute_of(params.until) if params.until else rush.DAY_MINUTES
    rush_hours = []
    for start, end, stats in windows:
        if end <= now or start >= until:
            continue
        stats.pop("busy_days", None)
        rush_hours.append(
            stats
            | {
                "status": "in_progress" if start <= now else "upcoming",
                "minutes_until": max(0, start - now),
                "actual_orders": (
                    sum(actual.get(s, 0) for s in range(start, end, slot)) if actual else None
                ),
            }
        )
    if not summary:
        summary = (
            f"{len(rush_hours)} rush window(s) expected from {params.from_time:%H:%M}"
            + (f" to {params.until:%H:%M}" if params.until else "")
            + f" on {params.on_date:%A %Y-%m-%d}."
            if fc.history
            else "Not enough history to forecast this day."
        )

    rush_slots = {s for start, end, _ in windows for s in range(start, end, slot)}
    shown = sorted(set(fc.expected) | set(actual))
    return {
        "date": params.on_date,
        "weekday": params.on_date.strftime("%A"),
        "time": params.from_time,
        "until": params.until,
        "slot_minutes": slot,
        "method": method,
        "model": model if method == "agent" else None,
        "history_days": sorted(fc.history),
        "typical_orders_per_slot": round(fc.typical, 2),
        "rush_threshold": round(fc.threshold, 2),
        "rush_hours": rush_hours,
        "slots": [
            {
                "start": rush.label(s),
                "expected_orders": round(fc.expected.get(s, 0.0), 2),
                "actual_orders": actual.get(s, 0) if actual else None,
                "is_rush": s in rush_slots,
            }
            for s in shown
            if now - now % slot <= s < until
        ],
        "summary": summary,
        "flags": flags,
        "agent_trace": trace,
    }
