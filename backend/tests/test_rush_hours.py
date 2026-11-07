"""Rush-hour forecast and agent over the seeded fixtures (12 orders, Friday 2026-05-01).

With 15-minute slots and all stores, that Friday has 1 order at 10:30, 5 at 11:00, 3 at
11:15, 2 at 11:30, and 1 at 11:45: typical 2.4 per active slot, rush threshold 3.6.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from nova_backend import rush_agent
from nova_backend.api import app
from nova_backend.db import get_session
from tests.test_imports import load

NEXT_FRIDAY = "2026-05-08"


@pytest.fixture
def client(engine, tmp_path, fixtures, monkeypatch):
    for source in ("doordash", "grubhub"):
        load(engine, tmp_path, fixtures, source)

    def session_override():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(rush_agent, "_openrouter", lambda: (None, "test/model"))
    app.dependency_overrides[get_session] = session_override
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def scripted(monkeypatch, replies):
    """Replace OpenRouter with canned assistant messages and record what was sent."""
    sent = []

    def chat(messages, tools, model):
        sent.append(json.loads(json.dumps(messages, default=str)))
        assert {t["function"]["name"] for t in tools} >= {"get_rush_forecast", "get_day_traffic"}
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(rush_agent, "_openrouter", lambda: ("test-key", "test/model"))
    monkeypatch.setattr(rush_agent, "_chat", chat)
    return sent


def call(name, args, call_id):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}


def test_baseline_forecast_finds_the_spike_without_a_key(client):
    response = client.get("/rush-hours", params={"date": NEXT_FRIDAY, "weeks": 1})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "baseline" and body["model"] is None
    assert body["weekday"] == "Friday"
    assert body["history_days"] == ["2026-05-01"]
    assert body["typical_orders_per_slot"] == 2.4 and body["rush_threshold"] == 3.6
    [window] = body["rush_hours"]
    assert (window["start"], window["end"], window["peak_at"]) == ("11:00", "11:15", "11:00")
    assert window["expected_orders"] == 5 and window["intensity"] == 2.08
    assert window["confidence"] == "low"  # One history day is not enough for more.
    assert window["status"] == "upcoming" and window["minutes_until"] == 660
    assert window["actual_orders"] is None  # 2026-05-08 has no recorded orders.
    assert any(flag.startswith("ai_unavailable") for flag in body["flags"])
    assert [s["start"] for s in body["slots"] if s["is_rush"]] == ["11:00"]


def test_time_input_returns_only_rushes_underway_or_ahead(client):
    during = client.get("/rush-hours", params={"date": NEXT_FRIDAY, "weeks": 1, "time": "11:05"})
    [window] = during.json()["rush_hours"]
    assert window["status"] == "in_progress" and window["minutes_until"] == 0
    after = client.get("/rush-hours", params={"date": NEXT_FRIDAY, "weeks": 1, "time": "11:15"})
    assert after.json()["rush_hours"] == []
    assert [s["start"] for s in after.json()["slots"]] == ["11:15", "11:30", "11:45"]
    before = client.get(
        "/rush-hours", params={"date": NEXT_FRIDAY, "weeks": 1, "time": "09:00", "until": "11:00"}
    )
    assert before.json()["rush_hours"] == []


def test_day_without_history_is_flagged_and_shows_actual_traffic(client):
    body = client.get("/rush-hours", params={"date": "2026-05-01"}).json()
    assert body["rush_hours"] == [] and body["history_days"] == []
    assert any(flag.startswith("no_history") for flag in body["flags"])
    assert sum(s["actual_orders"] for s in body["slots"]) == 12


def test_agent_investigates_then_python_recomputes_its_windows(client, monkeypatch):
    sent = scripted(
        monkeypatch,
        [
            {
                "content": None,
                "tool_calls": [
                    call("get_rush_forecast", "{}", "a"),
                    call("get_day_traffic", '{"date": "2026-05-01"}', "b"),
                    call("get_day_traffic", '{"date": "2026-05-08"}', "c"),
                ],
            },
            {
                "content": None,
                "tool_calls": [
                    call(
                        "count_orders",
                        '{"date_start": "2026-05-01", "date_end": "2026-05-02",'
                        ' "time_start": "11:00", "time_end": "11:30", "item_name": "burger"}',
                        "d",
                    ),
                    call(
                        "get_top_dishes",
                        '{"date_start": "2026-05-01", "date_end": "2026-05-02", "limit": 2}',
                        "e",
                    ),
                ],
            },
            {
                "content": "```json\n"
                + json.dumps(
                    {
                        "rush_hours": [
                            {
                                "start": "10:55",
                                "end": "11:20",
                                "multiplier": 3.0,
                                "confidence": "medium",
                                "reason": "Game day lunch.",
                            },
                            {"start": "11:15", "end": "11:45", "multiplier": 1},
                        ],
                        "summary": "One lunch rush, bigger than usual.",
                        "flags": ["event_day"],
                    }
                )
                + "\n```"
            },
        ],
    )
    response = client.get(
        "/rush-hours",
        params={"date": NEXT_FRIDAY, "weeks": 1, "time": "10:00", "context": "home game"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "agent" and body["model"] == "test/model"
    assert body["summary"] == "One lunch rush, bigger than usual."
    [window] = body["rush_hours"]
    # 10:55-11:20 snaps to 10:45-11:30; 3.0x clamps to 2.0x; (0 + 5 + 3) * 2 = 16.
    assert (window["start"], window["end"]) == ("10:45", "11:30")
    assert window["multiplier"] == 2.0 and window["clamped_from"] == 3.0
    assert window["expected_orders"] == 16 and window["expected_peak_orders"] == 10
    assert window["confidence"] == "medium" and window["reason"] == "Game day lunch."
    assert "event_day" in body["flags"]
    assert any(flag.startswith("ai_window_overlap") for flag in body["flags"])

    trace = {
        (step["tool"], step["args"].get("date")): step["result"] for step in body["agent_trace"]
    }
    assert "forecast rushes: 11:00-11:15" in trace[("get_rush_forecast", None)]
    assert "12 orders; spikes at 11:00" in trace[("get_day_traffic", "2026-05-01")]
    assert trace[("get_day_traffic", "2026-05-08")].startswith("error: Only days before")
    assert trace[("count_orders", None)] == "2 orders over 1 days"
    assert trace[("get_top_dishes", None)] == "Fountain Drink, Chicken Tender Basket"

    user_prompt = json.loads(sent[0][1]["content"].split("\n", 1)[1])
    assert user_prompt["manager_context"] == "home game" and user_prompt["weekday"] == "Friday"
    tool_replies = [m for m in sent[1] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_replies] == ["a", "b", "c"]
    assert json.loads(tool_replies[0]["content"])["rush_threshold"] == 3.6


@pytest.mark.parametrize(
    "reply",
    [
        RuntimeError,  # Replaced below with an AgentError.
        {"content": "I think lunch will be busy."},
        {"content": '{"summary": "no list"}'},
    ],
)
def test_agent_failure_falls_back_to_the_forecast(client, monkeypatch, reply):
    if reply is RuntimeError:
        reply = rush_agent.AgentError("OpenRouter returned HTTP 503")
    scripted(monkeypatch, [reply])
    body = client.get("/rush-hours", params={"date": NEXT_FRIDAY, "weeks": 1}).json()
    assert body["method"] == "baseline"
    assert [(w["start"], w["end"]) for w in body["rush_hours"]] == [("11:00", "11:15")]
    assert any(flag.startswith("ai_unavailable") for flag in body["flags"])


def test_use_agent_false_skips_openrouter(client, monkeypatch):
    scripted(monkeypatch, [])  # Any call would fail on the empty reply list.
    body = client.get(
        "/rush-hours", params={"date": NEXT_FRIDAY, "weeks": 1, "use_agent": "false"}
    ).json()
    assert body["method"] == "baseline" and body["agent_trace"] == []


def test_store_scope_and_slot_size(client):
    body = client.get(
        "/rush-hours",
        params={"date": NEXT_FRIDAY, "weeks": 1, "store_name": "strip", "slot_minutes": 30},
    ).json()
    # Strip District on that Friday: 4 orders at 11:00-11:30, 2 at 11:30-12:00. Typical is
    # 3, so the rush bar is 4.5 and neither slot is a spike.
    assert {s["start"]: s["expected_orders"] for s in body["slots"]} == {"11:00": 4, "11:30": 2}
    assert body["rush_threshold"] == 4.5 and body["rush_hours"] == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"date": NEXT_FRIDAY, "time": "12:00", "until": "11:00"},
        {"date": NEXT_FRIDAY, "weeks": 0},
        {"date": NEXT_FRIDAY, "slot_minutes": 20},
        {"date": NEXT_FRIDAY, "context": "x" * 501},
    ],
)
def test_rush_hours_rejects_invalid_input(client, params):
    assert client.get("/rush-hours", params=params).status_code == 400
