# Current integration scope

Ryan's explicit scope correction on November 7, 2026 supersedes older planning documents for this integration.

- Do not use David's recommendations spec (`handoffs/recommendations-spec.md`, also referred to as the "Veed spec") as implementation requirements.
- Build from the generated sales-only mock provider datasets, starting with `data/kstation_demo/`, through the sales API and sales/rush/dish analysis into the tablet UI.
- Do not add recipes, ingredient planning, inventory, camera integration, or prep calculations. Do not require those inputs to run the demo.
- Ground forecasts and explanations in available sales fields. Report limited history and distinguish observed sales from forecasts.
- Provider CSVs and normalized local API responses are synthetic simulations, not verified live provider API responses or connected restaurant accounts.
- Preserve unrelated work and datasets. Keep hackathon archives and ZIPs local; do not commit credentials or archived emails/Discord material.
- Before inspecting code, check and use the code-review graph if available.
