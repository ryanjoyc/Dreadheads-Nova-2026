"""Reconcile complete synthetic reports against a disposable PostgreSQL database.

Run through the Compose test service. This script intentionally clears only the
dedicated nova_sales_test database; it refuses a development database URL.
"""

import csv
import json
import os
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from nova_backend.db import engine
from nova_backend.imports import import_report
from nova_backend.models import Order, OrderLine, SourceStore

SOURCE_FILES = {
    "doordash": ("doordash_order_detail.csv", "store_id", "dd_order_number", "order_item_quantity"),
    "grubhub": (
        "grubhub_menu_line_items.csv",
        "grubhub_store_id",
        "order_uuid",
        "menu_item_quantity",
    ),
}


def expected_totals(path, store_column, order_column, quantity_column):
    # Independent stdlib reader: do not reuse provider parsers to set expectations.
    orders = set()
    count = 0
    quantity = Decimal(0)
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            count += 1
            orders.add((row[store_column], row[order_column]))
            quantity += Decimal(row[quantity_column])
    return {"orders": len(orders), "lines": count, "quantity": quantity}


def actual_totals(source):
    with Session(engine) as session:
        orders = session.scalar(
            select(func.count())
            .select_from(Order)
            .join(SourceStore)
            .where(SourceStore.source == source)
        )
        lines, quantity = session.execute(
            select(func.count(), func.coalesce(func.sum(OrderLine.quantity), 0))
            .select_from(OrderLine)
            .join(Order)
            .join(SourceStore)
            .where(SourceStore.source == source)
        ).one()
        return {"orders": orders, "lines": lines, "quantity": quantity}


def main():
    url = make_url(os.environ["DATABASE_URL"])
    test_url = os.environ.get("TEST_DATABASE_URL")
    if (
        url.database != "nova_sales_test"
        or url.host != "db-test"
        or not test_url
        or url != make_url(test_url)
    ):
        raise SystemExit("Refusing to clear a database other than Compose db-test/nova_sales_test")
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE order_lines, orders, source_stores, import_runs CASCADE"))
    base = Path("/workspace/data/nova_sample_data/nova_sample_data/data/platform_reports")
    expected = {}
    for source, (filename, store, order, quantity) in SOURCE_FILES.items():
        path = base / filename
        expected[source] = expected_totals(path, store, order, quantity)
        for attempt in (1, 2):
            run_id = import_report(source, path, synthetic=True, complete_orders=True)
            actual = actual_totals(source)
            assert actual == expected[source], (source, attempt, expected[source], actual)
            print(
                json.dumps(
                    {"source": source, "attempt": attempt, "import_id": str(run_id), **actual},
                    default=str,
                ),
                flush=True,
            )
    print("PASS: both full reports reconcile after initial import and replay", flush=True)


if __name__ == "__main__":
    main()
