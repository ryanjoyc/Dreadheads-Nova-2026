"""Atomic imports of explicitly synthetic, complete-order platform reports."""

import argparse
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from nova_backend import db
from nova_backend.config import get_settings
from nova_backend.models import ImportRun, Order, OrderLine, SourceStore
from nova_backend.parsing import ParsedReport, ReportValidationError, parse_report


class ImportFailure(ValueError):
    """A public-safe failure message and, if created, its persisted import ID."""

    def __init__(self, message: str, import_id: UUID | None = None):
        super().__init__(message)
        self.import_id = import_id


def chunks(rows: list, size: int = 1000):
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def persist_report(session: Session, source: str, report: ParsedReport, run_id: UUID):
    """Write one validated report. Caller owns its atomic transaction."""
    # Transaction-scoped, stable integer keys; do not use process-randomized hash().
    lock_key = 1313822273 + (source == "grubhub")
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    store_rows = [
        {
            "id": uuid4(),
            "source": source,
            "external_store_id": store.external_store_id,
            "store_name": store.store_name,
            "timezone": store.timezone,
            "source_details": store.source_details,
        }
        for store in report.stores.values()
    ]
    store_ids = {}
    for batch in chunks(store_rows):
        statement = pg_insert(SourceStore).values(batch)
        statement = statement.on_conflict_do_update(
            index_elements=[SourceStore.source, SourceStore.external_store_id],
            set_={
                key: getattr(statement.excluded, key)
                for key in ("store_name", "timezone", "source_details")
            },
        ).returning(SourceStore.id, SourceStore.external_store_id)
        store_ids.update({external: store_id for store_id, external in session.execute(statement)})
    order_rows = [
        {
            "id": uuid4(),
            "source_store_id": store_ids[order.external_store_id],
            "external_order_id": order.external_order_id,
            "order_number": order.order_number,
            "placed_at_local": order.placed_at_local,
            "source_timezone": order.source_timezone,
            "fulfillment": order.fulfillment,
            "subtotal": order.subtotal,
            "source_details": order.source_details,
            "last_import_run_id": run_id,
        }
        for order in report.orders.values()
    ]
    order_ids = {}
    for batch in chunks(order_rows):
        statement = pg_insert(Order).values(batch)
        statement = statement.on_conflict_do_update(
            index_elements=[Order.source_store_id, Order.external_order_id],
            set_={
                key: getattr(statement.excluded, key)
                for key in (
                    "order_number",
                    "placed_at_local",
                    "source_timezone",
                    "fulfillment",
                    "subtotal",
                    "source_details",
                    "last_import_run_id",
                )
            },
        ).returning(Order.id, Order.source_store_id, Order.external_order_id)
        order_ids.update(
            {
                (store_id, external): order_id
                for order_id, store_id, external in session.execute(statement)
            }
        )
    all_order_ids = list(order_ids.values())
    for batch in chunks(all_order_ids):
        session.execute(delete(OrderLine).where(OrderLine.order_id.in_(batch)))
    line_rows = []
    for order in report.orders.values():
        order_id = order_ids[(store_ids[order.external_store_id], order.external_order_id)]
        for line in order.lines:
            line_rows.append(
                {
                    "id": uuid4(),
                    "order_id": order_id,
                    "external_line_id": line.external_line_id,
                    "external_item_id": line.external_item_id,
                    "item_name": line.item_name,
                    "category_name": line.category_name,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "modifiers": line.modifiers,
                    "source_details": line.source_details,
                }
            )
    for batch in chunks(line_rows):
        session.execute(insert(OrderLine), batch)


def import_report(
    source: str,
    file: Path,
    synthetic: bool,
    complete_orders: bool,
    engine: Engine | None = None,
    raw_storage_path: Path | None = None,
    report_version: int | None = None,
    provider_report_id: str | None = None,
) -> UUID:
    """Validate a whole CSV, then atomically refresh its included complete orders.

    Only fixtures declared synthetic are accepted. ``complete_orders`` is a caller
    assertion, not a completeness guarantee inferred from CSV contents.
    """
    if source not in {"doordash", "grubhub"}:
        raise ImportFailure("Unsupported source")
    if not synthetic or not complete_orders:
        raise ImportFailure("This version requires --synthetic and --complete-orders")
    if source == "doordash":
        report_version = report_version if report_version is not None else 2
        if report_version < 2:
            raise ImportFailure("DoorDash report version 2 or later is required")
    elif report_version is not None:
        raise ImportFailure("Grubhub report_version is not supported")
    engine = engine if engine is not None else db.engine
    storage = Path(
        raw_storage_path if raw_storage_path is not None else get_settings().raw_storage_path
    )
    run_id = uuid4()
    started_at = datetime.now(UTC)
    raw_reference = f"{run_id}.csv"
    try:
        with Session(engine) as session, session.begin():
            session.add(
                ImportRun(
                    id=run_id,
                    source=source,
                    report_type="ORDER_DETAIL" if source == "doordash" else "menu-line-items",
                    report_version=report_version,
                    requested_columns=[],
                    provider_report_id=provider_report_id,
                    status="running",
                    started_at=started_at,
                    is_synthetic=True,
                    row_count=0,
                )
            )
    except Exception:
        raise ImportFailure("Unable to create import record; database unavailable") from None
    try:
        storage.mkdir(parents=True, exist_ok=True)
        raw_file = storage / raw_reference
        with Path(file).open("rb") as original, raw_file.open("xb") as archived:
            shutil.copyfileobj(original, archived)
        with Session(engine) as session, session.begin():
            session.get(ImportRun, run_id).raw_file_reference = raw_reference
        report = parse_report(source, raw_file)
        with Session(engine) as session, session.begin():
            run = session.get(ImportRun, run_id)
            run.requested_columns = report.columns
            run.row_count = report.row_count
            # These are observed file dates, not proof of full provider coverage.
            run.date_start = report.date_start
            run.date_end = report.date_end + timedelta(days=1) if report.date_end else None
        with Session(engine) as session, session.begin():
            persist_report(session, source, report, run_id)
            run = session.get(ImportRun, run_id)
            run.status = "succeeded"
            run.completed_at = datetime.now(UTC)
        return run_id
    except Exception as exc:
        if isinstance(exc, ReportValidationError):
            message = str(exc)
        elif isinstance(exc, OSError):
            message = "Unable to read or archive the input file"
        else:
            message = "Import persistence failed; sales changes were rolled back"
        try:
            with Session(engine) as session, session.begin():
                run = session.get(ImportRun, run_id)
                run.status = "failed"
                run.error = message
                run.completed_at = datetime.now(UTC)
        except Exception:
            raise ImportFailure(
                "Import failed; database unavailable to record failure", run_id
            ) from None
        raise ImportFailure(message, run_id) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=["doordash", "grubhub"])
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--complete-orders", action="store_true")
    parser.add_argument("--report-version", type=int)
    parser.add_argument("--provider-report-id")
    args = parser.parse_args()
    try:
        run_id = import_report(**vars(args))
    except ImportFailure as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(f"Imported synthetic {args.source} report: {run_id}")


if __name__ == "__main__":
    main()
