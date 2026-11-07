"""Export one explicitly selected synthetic store cohort through the existing HTTP API."""

import argparse
import gzip
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


def read_page(base_url, endpoint, params):
    with urlopen(f"{base_url.rstrip('/')}/{endpoint}?{urlencode(params)}", timeout=60) as response:
        return json.load(response)


def collect(base_url, endpoint, **filters):
    records, cursors = [], set()
    params = {"limit": 500, **filters}
    while True:
        page = read_page(base_url, endpoint, params)
        if not isinstance(page.get("data"), list) or "next_cursor" not in page:
            raise ValueError("Unexpected API page shape")
        records.extend(page["data"])
        cursor = page["next_cursor"]
        if cursor is None:
            return records
        if not isinstance(cursor, str) or cursor in cursors:
            raise ValueError("Repeated or invalid pagination cursor")
        cursors.add(cursor)
        params["cursor"] = cursor


def export_dataset(base_url: str, stores: list[str], output_dir: Path) -> dict:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "api"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use the local HTTP API or Compose api service")
    if not stores or len(set(stores)) != len(stores):
        raise ValueError("Select distinct source:external_store_id values")
    requested = set(stores)
    if any(s.split(":", 1)[0] not in {"doordash", "grubhub"} or ":" not in s for s in stores):
        raise ValueError("Store selections must be source:external_store_id")
    if output_dir.exists():
        raise FileExistsError("Export output already exists; choose a new directory")
    store_records = [
        row
        for row in collect(base_url, "stores")
        if f"{row['source']}:{row['external_store_id']}" in requested
    ]
    if len(store_records) != len(stores):
        raise ValueError("One or more requested stores are not present in the backend")
    orders, lines, items = [], [], []
    for store in store_records:
        filters = {"store_id": store["id"]}
        orders.extend(collect(base_url, "orders", **filters))
        lines.extend(collect(base_url, "order-lines", **filters))
        items.extend(collect(base_url, "items", **filters))
    order_by_id = {row["id"]: row for row in orders}
    if len(order_by_id) != len(orders) or len({row["id"] for row in lines}) != len(lines):
        raise ValueError("Duplicate records observed while paging")
    if not orders or not lines:
        raise ValueError("Selected stores have no sales history")
    for line in lines:
        order = order_by_id.get(line["order_id"])
        if (
            order is None
            or line["store_id"] != order["store_id"]
            or line["last_import_run_id"] != order["last_import_run_id"]
        ):
            raise ValueError(
                "Inconsistent order and line snapshots; retry without concurrent imports"
            )
    run_ids = {row["last_import_run_id"] for row in orders}
    imports = [row for row in collect(base_url, "imports") if row["id"] in run_ids]
    if {row["id"] for row in imports} != run_ids:
        raise ValueError("Missing import provenance")
    if any(row["status"] != "succeeded" for row in imports):
        raise ValueError("Export contains unsuccessful import provenance")
    if any(not row["is_synthetic"] for row in orders + lines + items + imports):
        raise ValueError("This export tool accepts only explicitly synthetic data")
    # A correction commits order metadata and lines atomically, and assigns a new
    # last_import_run_id. Comparing all orders again detects a mid-export import.
    orders_after = []
    for store in store_records:
        orders_after.extend(collect(base_url, "orders", store_id=store["id"]))
    if {row["id"]: row for row in orders_after} != order_by_id:
        raise ValueError("Sales changed during export; retry without concurrent imports")
    groups = {
        "stores": store_records,
        "orders": orders,
        "order_lines": lines,
        "items": items,
        "imports": imports,
    }
    totals = {
        "orders": len(orders),
        "order_lines": len(lines),
        "quantity": str(sum((Decimal(str(row["quantity"])) for row in lines), Decimal(0))),
        "orders_by_source": dict(Counter(row["source"] for row in orders)),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".export-", dir=output_dir.parent))
    try:
        files = {}
        for name, rows in groups.items():
            path = temporary / f"{name}.jsonl.gz"
            # Compression changes storage only; each JSON object is an unchanged API record.
            with gzip.open(path, "wt", encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
            files[path.name] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
        manifest = {
            "is_synthetic": True,
            "base_url": base_url,
            "stores": sorted(stores),
            "files": files,
            "totals": totals,
            "note": "Synthetic API exports only; no recipes, inventory, logs, or credentials.",
        }
        (temporary / "export_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.rename(output_dir)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--store", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = export_dataset(args.base_url, args.store, args.out)
    print(json.dumps(manifest["totals"], indent=2))


if __name__ == "__main__":
    main()
