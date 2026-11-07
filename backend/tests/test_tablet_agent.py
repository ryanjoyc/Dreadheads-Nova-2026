"""John's agent and the tablet adapter agree on scope, windows, and quantities."""

import json
from datetime import date

import pytest

from nova_backend import rush_agent, tablet
from tests.test_tablet_tools import row


def sample_rows():
    rows = [row(str(i), "2026-10-01", quantity=2) for i in range(6)]
    rows += [row("quiet", "2026-10-01", hour=15)]
    rows += [row("actual", "2026-10-08", quantity=99)]
    rows += [row("future", "2026-10-15", quantity=999)]
    return rows


def test_tablet_uses_johns_baseline_without_model_calls(monkeypatch):
    monkeypatch.setattr(tablet, "_cohort_lines", lambda *args: sample_rows())
    monkeypatch.setattr(rush_agent, "_openrouter", lambda: ("not-used", "test/model"))
    monkeypatch.setattr(rush_agent, "_chat", lambda *args: pytest.fail("Unexpected model call"))
    result = tablet.tablet_analysis(None, date(2026, 10, 8))
    assert result["analysis"]["method"] == "baseline"
    assert result["forecast"]["orders"] == 7
    assert result["forecast"]["rushes"][0]["expected_orders"] == 6
    assert "Recent Thursdays" in result["forecast"]["rushes"][0]["reason"]
    assert result["observed"]["dishes"][0]["quantity"] == 99


def test_agent_tools_and_multiplier_flow_into_exact_tablet_window_once(monkeypatch):
    monkeypatch.setattr(tablet, "_cohort_lines", lambda *args: sample_rows())
    monkeypatch.setattr(rush_agent, "_openrouter", lambda: ("test-key", "test/model"))
    messages_seen = []

    def scripted(messages, tools, model):
        messages_seen.append(json.loads(json.dumps(messages, default=str)))
        if len(messages_seen) == 1:
            return {
                "tool_calls": [
                    {"id": "forecast", "function": {"name": "get_rush_forecast", "arguments": "{}"}}
                ]
            }
        if len(messages_seen) == 2:
            assert '"history_days": ["2026-10-01"]' in messages[-1]["content"]
            return {
                "tool_calls": [
                    {
                        "id": "no-future",
                        "function": {
                            "name": "get_day_traffic",
                            "arguments": '{"date":"2026-10-08"}',
                        },
                    }
                ]
            }
        assert "Only days before" in messages[-1]["content"]
        return {
            "content": json.dumps(
                {
                    "rush_hours": [
                        {
                            "start": "12:00",
                            "end": "12:30",
                            "multiplier": 1.5,
                            "confidence": "high",
                            "reason": "Scripted adjustment for integration verification",
                        }
                    ],
                    "summary": "Adjusted window",
                    "flags": [],
                }
            )
        }

    monkeypatch.setattr(rush_agent, "_chat", scripted)
    result = tablet.tablet_analysis(None, date(2026, 10, 8), use_agent=True)
    assert result["analysis"]["method"] == "agent"
    assert len(result["analysis"]["agent_trace"]) == 2
    window = result["forecast"]["rushes"][0]
    assert (window["start"], window["end"]) == ("12:00", "12:30")
    assert window["confidence"] == "low"
    assert window["expected_orders"] == 9
    assert window["dishes"][0]["quantity"] == 18
    assert result["forecast"]["orders"] == 10
    assert result["forecast"]["dishes"][0]["quantity"] == 19
    assert result["observed"]["dishes"][0]["quantity"] == 99


def test_requested_agent_without_key_keeps_tablet_available(monkeypatch):
    monkeypatch.setattr(tablet, "_cohort_lines", lambda *args: sample_rows())
    monkeypatch.setattr(rush_agent, "_openrouter", lambda: (None, "test/model"))
    result = tablet.tablet_analysis(None, date(2026, 10, 8), use_agent=True, context="rain")
    assert result["analysis"]["method"] == "baseline"
    assert any("ai_unavailable" in flag for flag in result["analysis"]["flags"])
    assert any("context_ignored" in flag for flag in result["analysis"]["flags"])
    assert result["forecast"]["orders"] == 7


@pytest.mark.parametrize(
    "reply",
    [
        {"tool_calls": ["invalid"]},
        {"tool_calls": {"not": "a list"}},
        {"tool_calls": [{"id": "a", "function": {"name": "count_orders", "arguments": {}}}]},
        {"content": '{"rush_hours": [], "flags": 5}'},
        {"content": '{"rush_hours": [], "flags": [5]}'},
    ],
)
def test_malformed_model_fields_fall_back_instead_of_breaking_tablet(monkeypatch, reply):
    monkeypatch.setattr(tablet, "_cohort_lines", lambda *args: sample_rows())
    monkeypatch.setattr(rush_agent, "_openrouter", lambda: ("test-key", "test/model"))
    monkeypatch.setattr(rush_agent, "_chat", lambda *args: reply)
    result = tablet.tablet_analysis(None, date(2026, 10, 8), use_agent=True)
    assert result["analysis"]["method"] == "baseline"
    assert any("ai_unavailable" in flag for flag in result["analysis"]["flags"])
    assert result["forecast"]["orders"] == 7
