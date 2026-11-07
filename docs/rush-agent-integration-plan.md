# Integrate John's rush analysis

Goal: retain Kurt's tablet and the K-Station synthetic sales pipeline while using John's rush engine for windows, reasons, confidence, and optional AI adjustments.

- Merge latest main after committing the working local demo.
- Reuse John's forecasting math and agent orchestration with request-local tools bound to loaded K-Station records. Do not widen queries to other restaurants.
- Adapt returned windows into the tablet response; recompute canonical dish forecasts over those exact windows and apply each multiplier once.
- Keep whole-day totals and slot values consistent with window adjustments, and keep observations separate.
- Preserve the no-key/offline fallback, explicit optional AI control, and local approval demo.
- Test fallback, scripted model tool calls, changed windows/multipliers, scope isolation, and historical cutoff without paid requests. Verify the real browser flow after restarting the API.

## Verification result

John's `origin/main` through `7c06ea0` is merged. The tablet's daily endpoint uses his engine with request-local historical tools over the exact K-Station cohort. Optional AI/context inputs, returned reasons/confidence/trace, consistent order/dish adjustments, and baseline fallback are connected. The seven-day outlook remains deterministic.

Checks: 130 backend tests, 5 browser tests, frontend production build, changed-file Ruff, and git whitespace checks. Scripted model calls verify tool use, altered windows, single multiplier application, observed-sales preservation, and malformed-response fallback. No paid live model requests were made. Browser tests cover all time horizons, source filters, proposal approval/rejection, error/retry, responsive widths, and optional AI input/trace presentation.
