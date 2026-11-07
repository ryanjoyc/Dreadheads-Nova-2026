#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  ""|--backend-only) ;;
  *) echo "Usage: $0 [--backend-only]" >&2; exit 2 ;;
esac
backend_only="${1:-}"
cd "$(dirname "$0")/.."
project_root="$PWD"
cd backend
compose=(docker compose -f compose.yaml -f compose.demo.yaml)
"${compose[@]}" build tablet-api
"${compose[@]}" up -d db
"${compose[@]}" run --rm --no-deps tablet-api alembic upgrade head
"${compose[@]}" run --rm --no-deps tablet-api python -m nova_backend.imports --source doordash --file /workspace/data/kstation_demo/platform_reports/doordash_order_detail.csv --synthetic --complete-orders
"${compose[@]}" run --rm --no-deps tablet-api python -m nova_backend.imports --source grubhub --file /workspace/data/kstation_demo/platform_reports/grubhub_menu_line_items.csv --synthetic --complete-orders
"${compose[@]}" up -d --no-deps --wait tablet-api
if [[ "$backend_only" == "--backend-only" ]]; then
  echo "Demo API ready at http://127.0.0.1:8003; existing frontend can stay open."
  exit 0
fi
cd "$project_root/frontend"
if [[ ! -d node_modules ]]; then npm ci; fi
exec npm run dev
