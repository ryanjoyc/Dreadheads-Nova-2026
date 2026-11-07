# Backend: prep recommendation agent

A FastAPI service that turns the synthetic DoorDash and Grubhub history in `data/` into a prep sheet, a rush timeline, and heads-up flags (see [the spec](../handoffs/recommendations-spec.md)). It follows the NOVA Tech Guide: FastAPI, OpenRouter, and tool calls.

**Rule:** plain Python does every calculation. The LLM investigates with tools, then returns multipliers between 0.5× and 2.0×, each with a reason. Python clamps those multipliers and recomputes every quantity.

## Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # then paste the team key after OPENROUTER_KEY=
.venv\Scripts\uvicorn main:app --reload --port 8000
```

Open http://localhost:8000/docs to try each endpoint. Never commit `.env`: OpenRouter disables any key it finds in a repo, even a private one. The repo's `.gitignore` already excludes `.env`.

Without a key, everything still works: the plan falls back to the plain historical baseline and adds a flag saying the AI adjustment is unavailable.

## Endpoints

| Endpoint | What it returns |
|---|---|
| `POST /recommendations` | Everything below in one response, plus the agent's tool trace and a backtest when the date is in history |
| `GET /prep-sheet?date=&location=` | Feature 1 rows (sorted by hold time, longest first) and Feature 3 flags |
| `GET /timeline?date=&location=` | Feature 2: batch start times and peak hours |
| `GET /heatmap?location=&metric=orders\|M10&channel=all\|doordash\|grubhub` | Feature 4: days × 15-minute slots |
| `POST /chat_streaming` | Free-form chat about the data with tools, streamed (Tech Guide format) |
| `GET /meta`, `GET /health` | Locations, date range, menu, components; whether a key is set |

`POST /recommendations` body:

```json
{
  "location": "strip",
  "date": "2026-11-08",
  "context": {"local_event": "Pro football home game", "weather": "rain"},
  "on_hand": {"C01": 40},
  "use_agent": true
}
```

`context` is what the manager knows about the day that the calendar doesn't. The calendar covers only May–Oct 2026, so future dates need it. Results are cached per request body; add `?refresh=true` to rerun the agent.

Each `prep_sheet` row has `need`, `on_hand`, `to_prep` (rounded up to whole batches), `need_by_daypart`, `reason`, and `confidence`. The `agent.trace` field lists each tool the agent called with a one-line result, which the UI can show as "how the AI decided".

## How the agent decides

`services/agent.py` gives the model five read-only tools (`services/tools.py`):

| Tool | Purpose |
|---|---|
| `get_day_context` | Weather, holiday, event, university session (plus manager input) |
| `get_baseline` | Average of the last 8 same weekdays, special days excluded |
| `find_similar_days` | Past games, holidays, rain days, etc., each compared with its own baseline |
| `get_stockout_history` | What ran out on recent same weekdays |
| `preview_prep_plan` | Check the totals that candidate multipliers would produce |

The model returns JSON with daypart multipliers, component multipliers, flags, and a summary. `_normalize_decision` clamps the values and records any clamping (`clamped_from`), and `DataStore.prep_plan` does the math.

The guide routes tools through MCP servers. Ours are local Python functions, so we pass the same OpenAI-style tool definitions straight to OpenRouter. Other differences from the guide's sample code: async `httpx` instead of blocking `requests`, and the tool-call helpers the guide leaves out are implemented here.

## Demo scenarios

| Scenario | Request | What to show |
|---|---|---|
| Normal day | `strip`, `2026-10-20` (Tuesday) | Prep sheet sorted by hold time; multipliers near 1.0 |
| Game day (happy path) | `strip`, `2026-10-25` | The agent finds the 2 earlier home games (1.40×, 1.54×) and raises amounts. The backtest compares the plan with the manager's real prep (169 actual orders vs a 113 baseline) |
| Future game day | `strip`, `2026-11-08` + `{"local_event": "Pro football home game"}` | Manager-entered context drives the adjustment |
| Sad path: no history | a date + `{"holiday": "Thanksgiving"}` | No similar days, so confidence is low and an `unusual_day` flag appears |
| Sad path: AI down | `"use_agent": false` or no key | Baseline-only plan with a clear flag |

## Streaming chat for the frontend

`POST /chat_streaming` takes the Tech Guide's `ChatRequest` (`model_id`, `chat_history`, `use_mcp`). Here `use_mcp` turns on our data tools, and it defaults to true. The response is NDJSON, one JSON object per line:

- OpenRouter chunks: read `choices[0].delta.content` and append it.
- `{"type": "tool_call", "name": ..., "args": ..., "ok": true}`: show as "checking past game days…".
- `{"type": "error", "error": ...}`.

The guide's React hook decodes each chunk on its own, which can split lines. Buffer the text and split it on `\n` before calling `JSON.parse`.

## Files

```
main.py                    FastAPI routes
models/schemas.py          request models (ChatRequest follows the guide)
services/data_service.py   load and merge CSVs, baseline, similar days, stock-outs, prep plan, timeline, heatmap, backtest
services/tools.py          tool definitions + executor
services/agent.py          recommendation agent loop + fallback
services/chat_service.py   streaming chat with tool calls
services/openrouter.py     key loading and API calls
```
