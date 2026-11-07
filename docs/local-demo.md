# Run the K-Station sales tablet

From the `NOVA 2026-integration` checkout, with Docker running and Node/npm installed:

```sh
./scripts/demo.sh
```

Open http://127.0.0.1:5173. The script builds a separate demo API, starts PostgreSQL if needed, applies migrations, imports both K-Station CSVs, and starts Vite. Existing restaurant records are preserved. Reimporting the same complete-order reports updates this cohort without duplicating orders; each import creates an audit record.

The sales API already running on port 8000 remains available. The demo API uses port 8003 and the same development database. Its interactive API documentation is at http://127.0.0.1:8003/docs. The separate legacy recipe agent service is not used. The tablet uses John's sales-only rush engine. Baseline mode requires no key or model call. Optional AI mode is described below.

If the tablet is already running, use that tab instead of launching a second Vite process on port 5173. Press Ctrl-C in the terminal running Vite to stop it. Stop only the demo API with:

```sh
cd backend
docker compose -f compose.yaml -f compose.demo.yaml stop tablet-api
```

Do not remove volumes to stop the demo.

## Show the demo

The tablet follows Kurt's time-based navigation and dish/count rows. Demo date, time, scenario shortcuts, and feed filters are under the collapsed **Demo settings** above the tablet.

- **Next rush:** expected dish sales in the next predicted busy window after the selected demo time.
- **Rest of today:** remaining busy windows and their expected dish sales.
- **Tomorrow:** tomorrow's rushes and whole-day dish outlook.
- **Further ahead:** seven-day expected dish sales and daily order totals.
- **Setup:** comparison dates, forecast-versus-observed totals, source explanation, and limitations.

Start on October 29 at 09:30. Its forecast uses four earlier Thursdays: 754.8 expected orders, versus 778 observed that day. The tablet rounds display counts to whole numbers. Switch to Quiet Sunday or One-off spike under Demo settings to compare scenarios. An isolated spike has no invented cause and is not automatically predicted from later records.

## What flows through the app

```text
Synthetic provider CSV reports
  → existing importer and PostgreSQL
  → /tablet and /tablet/outlook on the sales API
  → deterministic sales analysis
  → tablet rush windows and dish counts
```

The API reads through the existing paginated sales query functions. John's rush engine and its request-local tools then analyze that same K-Station snapshot. It selects DoorDash store `9900201` and Grubhub store `8800201`; other demo restaurants are excluded. Cross-platform dishes use the explicit synthetic manifest mapping. Date/feed changes fetch new results. The browser caches results until **Load day**, a scenario change, or a page reload; use Load day after reimporting data.

Forecasts average up to eight weeks of earlier matching weekdays with recorded sales. Missing dates are not assumed closed. Every seven-day outlook uses only records before its original start date. Target-day observations are shown separately and never enter that date's forecast. Zero-history selections show an empty state rather than an invented estimate. Rushes are adjacent 15-minute slots meeting a 1.5× active-slot mean threshold, with at least two expected orders per slot.

The source data is fabricated sales/report data, not a verified live provider response or real restaurant account connection. The monthly history has few matching weekdays. These forecasts demonstrate the pipeline, not real-world accuracy. Dish forecasts are expected sales, not ingredient or preparation instructions.

## Verify changes

With the app running:

```sh
npm ci --prefix frontend
npm run build --prefix frontend
npm run test:e2e --prefix frontend
```

Browser tests use an installed Chrome and the running app. They exercise the real API, time-horizon navigation, feed filters, no-history and failure/retry states, and widths from 280 to 768 pixels. A screenshot is saved locally in `output/kstation-demo.png`.

Run backend verification from `backend/`:

```sh
docker compose --profile test run --rm -v "$PWD:/app" test pytest -q
docker compose -f compose.yaml -f compose.demo.yaml run --rm --no-deps -v "$PWD:/app" tablet-api ruff check nova_backend/api.py nova_backend/tablet.py tests/test_tablet.py tests/test_tablet_api.py
```

The database test suite uses the dedicated disposable test database. It does not clear development sales.

To rebuild/reimport only the backend while keeping an existing Vite process open, run `./scripts/demo.sh --backend-only` from the checkout root, then use **Load day** or refresh the tablet.

## Demo a proposed rush

Use October 29 at 09:30 with Both feeds. The demo standing rush windows are explicitly configured in the UI as lunch 11:00–14:00 and dinner 17:00–20:30; these are demo choices, not provider fields or inferred restaurant settings.

The sales forecast detects a 14:30–14:45 window outside those standing windows. It appears as a proposal on Next rush and Rest of today. Its dish counts are withheld until **Approve for today** is selected. Approval adds its calculated dish counts to Rest of today in time order. **Reject rush** excludes it; **Review again** returns it to pending.

Decisions are browser-memory demo state, scoped to the selected date, feed, and time window. They reset on page reload and do not create a standing rush for future days or save to the backend. Tomorrow and the seven-day outlook remain sales estimates, not approved schedules.

## Optional AI-assisted rush analysis

The default is historical baseline mode. Expand Demo settings, enter optional day context, enable **Use AI analysis**, and select Load day to request the model-assisted path. Put `OPENROUTER_KEY` in `backend/.env`, keep it local, and recreate the demo API with the Compose files above after changing it. The key is read by the backend, never the browser.

`GET /tablet` accepts `use_agent=false|true` and optional `context` (up to 500 characters). It binds all four of John's tools to the exact loaded K-Station cohort and strictly earlier historical rows. The model can propose different rush windows and bounded multipliers; Python recalculates the window's order and canonical dish forecasts, slot counts, and whole-day totals. Observed sales stay unadjusted. Fewer than three comparison days force low confidence.

Setup displays baseline versus AI-assisted method, summary, fallback flags, and the agent tool trace when available. If the key is missing or the model fails, the tablet retains the historical forecast with a visible fallback explanation in Setup. Changing AI/context settings and selecting Load day clears the browser response cache. Further ahead remains a deterministic seven-day outlook with historical input frozen before its start date; the AI checkbox affects single-day rush analysis only.

The integration was verified with scripted model replies and failures; verification does not require spending credits on live model requests.
