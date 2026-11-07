"""
The recommendation agent (spec features 1-3: prep sheet, rush timeline, heads-up flags).

1. Python computes a baseline from history.
2. The LLM investigates with tools and returns bounded multipliers + reasons + flags as JSON.
3. Python clamps the multipliers to 0.5x-2.0x and recomputes every quantity itself.

If the LLM is unavailable or returns junk, we fall back to the plain baseline and say so.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from typing import Any, Dict, List, Optional

from services.data_service import (
    DAYPART_NAMES,
    DEFAULT_BUFFER,
    MULT_MAX,
    MULT_MIN,
    WEEKDAYS,
    clamp_multiplier,
    get_store,
)
from services.openrouter import DEFAULT_MODEL, OpenRouterError, chat_completion
from services.tools import TOOL_DEFINITIONS, ToolContext, execute_tool, parse_tool_args

MAX_TOOL_ROUNDS = 8
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
FLAG_TYPES = {"event", "stockout_risk", "channel_shift", "unusual_day"}


def system_prompt() -> str:
    store = get_store()
    labels = store.special_day_labels()
    components = ", ".join(f"{cid}={r.component_name}" for cid, r in store.comp.iterrows())
    return f"""You are the prep-planning assistant for Steel City Bowls, a fictional fast-casual restaurant with two Pittsburgh locations (craig: student-heavy; strip: office lunch, weekend and game-day crowds). All data is SYNTHETIC.

A shift manager needs a prep plan for a target date. Python already computes a baseline: the average of the last 8 same weekdays, with holidays and events excluded. You never invent quantities. Your job is to decide whether the target day's context justifies adjusting that baseline, using evidence from tools, and to explain each change in plain English a line cook would understand.

How to work:
1. Call get_day_context for the target date and get_baseline for the location and date.
2. Check whether the baseline days resemble the target day (university session, weather). If the target day has a holiday, event, notable weather, or a different university status than the baseline days, call find_similar_days to measure the effect on past days.
3. Call get_stockout_history. Repeated run-outs mean recorded sales understate demand for that component.
4. Optionally call preview_prep_plan to sanity-check your multipliers.

Rules:
- Every multiplier must be between {MULT_MIN} and {MULT_MAX}. 1.0 means no change. Use daypart multipliers for overall demand shifts and component multipliers for specific ingredients (for example, ones that keep running out).
- Base every number you cite on a tool result. If fewer than 2 comparable past days exist, keep multipliers near 1.0 and use confidence "low".
- Reasons must be short (under 25 words) and cite the evidence, for example "Last 2 home games ran 1.40x and 1.54x baseline".
- 0-4 flags, most important first. Flag types: event, stockout_risk, channel_shift (delivery share is high or shifts, so packaging matters), unusual_day (little or no history, or the date is outside the calendar).

Known special days in history: holidays {labels['holidays']}; events {labels['local_events']}.
Components: {components}.

When finished, reply with ONLY this JSON object and no other text:
{{
  "summary": "1-2 sentences for the manager",
  "daypart_multipliers": {{
    "lunch": {{"value": 1.0, "reason": "...", "confidence": "high|medium|low"}},
    "afternoon": {{...}}, "dinner": {{...}}, "late": {{...}}
  }},
  "component_multipliers": [{{"component_id": "C01", "value": 1.1, "reason": "..."}}],
  "flags": [{{"type": "event", "message": "...", "action": "...", "evidence": "..."}}]
}}"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _summarize_result(name: str, result: Dict[str, Any]) -> str:
    """One line per tool call for the UI's 'how the agent decided' panel."""
    if "error" in result:
        return f"error: {result['error']}"
    if name == "get_day_context":
        bits = [result.get("weekday"), result.get("weather"), result.get("holiday"), result.get("local_event")]
        if result.get("university_in_session") is not None:
            bits.append("university in session" if result["university_in_session"] else "university out")
        if not result.get("in_calendar"):
            bits.append("not in calendar")
        return ", ".join(str(b) for b in bits if b)
    if name == "get_baseline":
        return f"{result['avg_daily_orders']} orders/day from {len(result['baseline_days'])} past same weekdays"
    if name == "find_similar_days":
        return f"{result['count']} matching days, mean {result['mean_ratio_vs_baseline']}x baseline"
    if name == "get_stockout_history":
        top = list(result["runout_counts"].items())[:3]
        return "run-outs: " + (", ".join(f"{k} x{v}" for k, v in top) or "none")
    if name == "preview_prep_plan":
        return f"previewed {len(result['components'])} components"
    return "ok"


async def run_agent(
    location: str,
    target: str,
    overrides: Dict[str, Any],
    on_hand: Dict[str, float],
    model: Optional[str],
) -> Dict[str, Any]:
    """Returns the agent's raw decision plus a trace. Raises OpenRouterError on failure."""
    ctx = ToolContext(target, overrides)
    store = get_store()
    weekday = WEEKDAYS[date.fromisoformat(target).weekday()]
    user = (
        f"Plan prep for location '{location}' on {target} ({weekday}). "
        f"Data covers {store.first_date} to {store.last_date}."
    )
    if overrides:
        user += f" The manager entered this context for the target date: {json.dumps(overrides)}."
    if on_hand:
        user += f" On hand now: {json.dumps(on_hand)}."

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": user},
    ]
    trace: List[Dict[str, Any]] = []

    for round_no in range(MAX_TOOL_ROUNDS + 1):
        last_round = round_no == MAX_TOOL_ROUNDS
        data = await chat_completion(
            messages,
            model=model,
            tools=TOOL_DEFINITIONS,
            tool_choice="none" if last_round else None,
        )
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if tool_calls and not last_round:
            messages.append(
                {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
            )
            for call in tool_calls:
                name = call["function"]["name"]
                args = parse_tool_args(call["function"].get("arguments"))
                result = execute_tool(name, args, ctx)
                trace.append({"tool": name, "args": args, "result": _summarize_result(name, result)})
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, default=str)}
                )
            continue

        decision = _extract_json(msg.get("content") or "")
        if decision is None:
            # One retry asking for just the JSON.
            messages.append({"role": "assistant", "content": msg.get("content") or ""})
            messages.append({"role": "user", "content": "Reply with only the JSON object described above."})
            data = await chat_completion(messages, model=model)
            decision = _extract_json(data["choices"][0]["message"].get("content") or "")
        if decision is None:
            raise OpenRouterError("Model did not return valid JSON")
        return {"decision": decision, "trace": trace, "model": data.get("model", model or DEFAULT_MODEL)}

    raise OpenRouterError("Agent did not finish")


def _normalize_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp everything the model said into the allowed shape. Records any clamping."""
    dayparts = {}
    raw_dp = decision.get("daypart_multipliers") or {}
    for dp in DAYPART_NAMES:
        entry = raw_dp.get(dp) or {}
        if not isinstance(entry, dict):
            entry = {"value": entry}
        raw_value = entry.get("value", 1.0)
        value = clamp_multiplier(raw_value)
        conf = str(entry.get("confidence", "low")).lower()
        out = {
            "value": value,
            "reason": entry.get("reason") or "No change from baseline",
            "confidence": conf if conf in CONFIDENCE_ORDER else "low",
        }
        try:
            if float(raw_value) != value:
                out["clamped_from"] = float(raw_value)
        except (TypeError, ValueError):
            out["clamped_from"] = raw_value
        dayparts[dp] = out

    store = get_store()
    components = []
    for entry in decision.get("component_multipliers") or []:
        cid = entry.get("component_id")
        if cid not in store.comp.index:
            continue
        value = clamp_multiplier(entry.get("value", 1.0))
        out = {"component_id": cid, "value": value, "reason": entry.get("reason") or ""}
        try:
            if float(entry.get("value", 1.0)) != value:
                out["clamped_from"] = float(entry["value"])
        except (TypeError, ValueError):
            pass
        components.append(out)

    flags = []
    for f in (decision.get("flags") or [])[:4]:
        if not isinstance(f, dict):
            continue
        flags.append(
            {
                "type": f.get("type") if f.get("type") in FLAG_TYPES else "unusual_day",
                "message": f.get("message", ""),
                "action": f.get("action", ""),
                "evidence": f.get("evidence", ""),
            }
        )
    return {
        "summary": decision.get("summary", ""),
        "daypart_multipliers": dayparts,
        "component_multipliers": components,
        "flags": flags,
    }


def _baseline_only_decision(reason: str) -> Dict[str, Any]:
    return {
        "summary": "Showing the historical baseline only. The AI adjustment is unavailable, so check special days by hand.",
        "daypart_multipliers": {
            dp: {"value": 1.0, "reason": "Baseline only (AI unavailable)", "confidence": "low"}
            for dp in DAYPART_NAMES
        },
        "component_multipliers": [],
        "flags": [
            {
                "type": "unusual_day",
                "message": "AI adjustment unavailable; plan uses plain history",
                "action": "Check for events, holidays, or weather before prepping",
                "evidence": reason,
            }
        ],
    }


def _row_reason(row: Dict[str, Any], decision: Dict[str, Any], n_days: int, weekday: str) -> str:
    parts = [f"Baseline {row['baseline_need']:g} {row['unit']} (avg of {n_days} {weekday}s)"]
    total = sum(row["need_by_daypart"].values()) or 1
    for dp, m in decision["daypart_multipliers"].items():
        if m["value"] != 1.0 and row["need_by_daypart"][dp] / total >= 0.1:
            parts.append(f"{dp} x{m['value']:g}: {m['reason']}")
    for cm in decision["component_multipliers"]:
        if cm["component_id"] == row["component_id"]:
            parts.append(f"x{cm['value']:g}: {cm['reason']}")
    parts.append(f"+{int(DEFAULT_BUFFER * 100)}% buffer")
    if row["modifier_estimate"] >= 1:
        parts.append(f"incl. ~{row['modifier_estimate']:g} {row['unit']} for add-ons (Grubhub-based estimate)")
    return "; ".join(parts)


def _row_confidence(row: Dict[str, Any], decision: Dict[str, Any]) -> str:
    total = sum(row["need_by_daypart"].values()) or 1
    levels = [
        m["confidence"]
        for dp, m in decision["daypart_multipliers"].items()
        if row["need_by_daypart"][dp] / total >= 0.1
    ] or ["low"]
    return min(levels, key=lambda c: CONFIDENCE_ORDER[c])


async def recommend(
    location: str,
    target: str,
    overrides: Optional[Dict[str, Any]] = None,
    on_hand: Optional[Dict[str, float]] = None,
    model: Optional[str] = None,
    use_agent: bool = True,
) -> Dict[str, Any]:
    store = get_store()
    overrides = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
    on_hand = on_hand or {}
    started = time.time()

    agent_info: Dict[str, Any] = {"used": False, "model": None, "trace": []}
    if use_agent:
        try:
            result = await run_agent(location, target, overrides, on_hand, model)
            decision = _normalize_decision(result["decision"])
            agent_info.update(used=True, model=result["model"], trace=result["trace"])
        except Exception as e:
            decision = _baseline_only_decision(str(e))
            agent_info["error"] = str(e)
    else:
        decision = _baseline_only_decision("Agent turned off for this request")

    dp_mult = {dp: m["value"] for dp, m in decision["daypart_multipliers"].items()}
    comp_mult = {c["component_id"]: c["value"] for c in decision["component_multipliers"]}
    plan = store.prep_plan(location, target, dp_mult, comp_mult, DEFAULT_BUFFER, on_hand)

    weekday = WEEKDAYS[date.fromisoformat(target).weekday()]
    n_days = len(plan["baseline_days"])
    for row in plan["prep_sheet"]:
        row["reason"] = _row_reason(row, decision, n_days, weekday)
        row["confidence"] = _row_confidence(row, decision)

    flags = decision["flags"]
    if n_days < 4:
        flags.append(
            {
                "type": "unusual_day",
                "message": f"Only {n_days} past {weekday}s in the baseline",
                "action": "Treat amounts as rough",
                "evidence": f"Baseline days: {plan['baseline_days']}",
            }
        )

    agent_info["seconds"] = round(time.time() - started, 1)
    return {
        "data_label": "SYNTHETIC",
        "location": location,
        "date": target,
        "weekday": weekday,
        "context": store.get_context(target, overrides),
        "summary": decision["summary"],
        "flags": flags[:4],
        "daypart_multipliers": decision["daypart_multipliers"],
        "component_multipliers": decision["component_multipliers"],
        "prep_sheet": plan["prep_sheet"],
        "timeline": plan["timeline"],
        "open": plan["open"],
        "close": plan["close"],
        "baseline_days": plan["baseline_days"],
        "backtest": store.backtest(location, target, plan),
        "agent": agent_info,
        "caveat": "Sales data doesn't capture waste, spoilage, or true demand on sold-out days. "
        "Review before prepping.",
    }
