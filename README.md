# Dreadheads-Nova-2026
Team project for the NOVA 2026 hackathon at Carnegie Mellon University.

See [hackathon context](docs/hackathon-context.md) for rules, schedule, submission requirements, sponsor guidance, and official source links.

- [Glossary](GLOSSARY.md) — dishes, rushes, prep lists, and service windows
- [Recommendations spec](handoffs/recommendations-spec.md) — how a prep count is computed and what the tablet shows
- [Restaurant API data](handoffs/restaurant-api-data-handoff.md) — DoorDash and Grubhub order fields

Open [wireframes/prep.html](wireframes/prep.html) in a browser for the working prep tablet. Its sample day lives in [wireframes/mock-data.js](wireframes/mock-data.js).

The [prep frontend](frontend) is the same tablet as an app. Counts are placeholders in `frontend/src/placeholders.js` until recommendations data is ready. From `frontend/`, run `npm install` and `npm run dev`.

The [sales backend](backend/README.md) runs locally with FastAPI and PostgreSQL through Docker Compose. It imports synthetic DoorDash/Grubhub CSVs and exposes five read endpoints for analytics development.
