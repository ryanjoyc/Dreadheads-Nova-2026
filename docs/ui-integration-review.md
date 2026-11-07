# Tablet integration direction

Domain: restaurant sales planning. Audience: shift lead checking a tablet briefly. Tone: direct and practical. Motion: none. Reference: Kurt's original prep tablet, with the same shell, time navigation, and dish/count rows.

The first integration drifted into an analytics dashboard. Major findings: chart and form controls preceded actionable dish counts (hierarchy); navigation changed from time horizons to implementation categories (consistency and recognition); technical data explanations occupied the main flow (unnecessary reader load).

Correction: restore Next rush, Rest of today, Tomorrow, Further ahead, and Setup. Show expected dish sales directly for each rush window. Date/feed controls belong in collapsible demo settings. Keep technical provenance available in Setup. Preserve loading, empty, error, and retry behavior. Do not reinstate recipes or ingredient views.

## Final verification

Restored the original tablet shell, time-horizon navigation, and dish/count rows. The main view has no chart or large analytics summaries. Demo controls are collapsed above the tablet; calculation evidence is in Setup.

Reviewer assessment (subjective, not a conformance certification): hierarchy 8/10, consistency 8/10, accessibility 7/10, usability 8/10, responsiveness 8/10, performance 8/10. Weighted overall: 7.8/10. Accessibility remains a partial assessment: browser navigation, live status/error messages, responsive layout, and interactive text contrast were checked; a full screen-reader audit was not performed. The inherited interface is light themed; forcing a dark attribute does not establish a separate dark theme.

Measured project checks:
- Backend: 98 passed; one upstream Starlette/httpx deprecation warning.
- Browser: 3 passed, covering real API navigation and filters, empty/error/retry, and narrow viewports.
- Frontend production build passed; backend changed-file Ruff checks passed; git diff whitespace check passed.
- Rendered snapshot: 41 element states checked in default/hover/focus, all passing the state contrast check. Repeating with the dark attribute also passed, but is the same inherited light theme.
- Rendered snapshot responsive check: no horizontal overflow at 280/320/414 pixels. Live browser tests also checked 768 pixels.
- Startup script: backend-only path built the API, applied migrations, reimported both K-Station reports, and started the service successfully.

The generic design-kit accuracy command returned `RESULT: 0/52 checks passed = 0%` from this repository: it expects its own starter-kit scripts, token files, and harnesses that are absent here. That result is not counted as a passing project gate. The app-specific checks above were run against the actual Vite app and API.

Remaining enhancement: distinguish uncertain forecasts more prominently when only one or two matching weekdays exist. The current UI displays the actual historical count and an explicit no-history state; synthetic data does not establish real forecast accuracy.
