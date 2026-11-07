# K-Station sales tablet demo

Scope: synthetic K-Station sales records → the existing PostgreSQL sales API → deterministic traffic and dish analysis → tablet UI. David's recommendation spec and recipe-based agent are outside this work.

Acceptance:
- Read only K-Station's two explicit platform stores; preserve other datasets and existing services.
- Forecast a selected date from strictly earlier same weekdays, with visible sample count and limitations.
- Show rush windows, expected order volume, projected popular dishes, and historical-versus-observed comparison.
- Filter by all feeds, DoorDash, or Grubhub; changing date or feed updates the displayed data.
- Handle loading, empty history, validation, and backend errors without showing stale results.
- Provide repeatable local startup, test the calculations, and inspect the real tablet in a browser.

Use a separate demo API port so the existing running sales backend stays available. No model calls or API keys are required for deterministic sales analysis. The legacy recipe agent is retained as existing code but is not loaded by the demo.
