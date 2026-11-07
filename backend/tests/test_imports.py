import csv
from decimal import Decimal

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from nova_backend.imports import ImportFailure, import_report
from nova_backend.models import ImportRun, Order, OrderLine, SourceStore


def read_csv(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def write_csv(path, headers, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return path


def load(engine, tmp_path, fixtures, source):
    name = "doordash_order_detail.csv" if source == "doordash" else "grubhub_menu_line_items.csv"
    return import_report(
        source, fixtures / name, True, True, engine=engine, raw_storage_path=tmp_path / "raw"
    )


def totals(engine):
    with Session(engine) as session:
        return (
            session.scalar(select(func.count()).select_from(SourceStore)),
            session.scalar(select(func.count()).select_from(Order)),
            session.scalar(select(func.count()).select_from(OrderLine)),
            session.scalar(select(func.sum(OrderLine.quantity))),
        )


def test_fixture_mapping_and_replay(engine, tmp_path, fixtures):
    for source in ["doordash", "grubhub"]:
        load(engine, tmp_path, fixtures, source)
    before = totals(engine)
    assert before[:3] == (4, 12, 21)
    with Session(engine) as session:
        orders_before = set(session.scalars(select(Order.id)))
        dd_store_ids = {
            s.external_store_id
            for s in session.scalars(select(SourceStore).where(SourceStore.source == "doordash"))
        }
        assert dd_store_ids == {"24418903", "24418977"}
        gh_orders = session.scalars(
            select(Order).join(SourceStore).where(SourceStore.source == "grubhub")
        ).all()
        assert all(o.subtotal is None and o.order_number for o in gh_orders)
        assert all(len(o.external_order_id) == 36 for o in gh_orders)
        assert all(o.placed_at_local.tzinfo is None for o in gh_orders)
        assert all(o.source_timezone == "America/New_York" for o in gh_orders)
        assert all(r.is_synthetic for r in session.scalars(select(ImportRun)))
        assert any(line.source_details for line in session.scalars(select(OrderLine)))
    for source in ["doordash", "grubhub"]:
        load(engine, tmp_path, fixtures, source)
    assert totals(engine) == before
    with Session(engine) as session:
        assert set(session.scalars(select(Order.id))) == orders_before


def test_complete_order_correction_and_repeated_dish(engine, tmp_path, fixtures):
    headers, rows = read_csv(fixtures / "grubhub_menu_line_items.csv")
    first = rows[0]
    one_order = [r.copy() for r in rows if r["order_uuid"] == first["order_uuid"]]
    repeated = one_order[0].copy()
    repeated["menu_item_quantity"] = "4"
    repeated["menu_item_modifiers"] = '[{"id":"extra","name":"Extra","price":1,"quantity":1}]'
    one_order.append(repeated)
    path = write_csv(tmp_path / "repeated.csv", headers, one_order)
    import_report("grubhub", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw")
    with Session(engine) as session:
        stable_id = session.scalar(select(Order.id))
        assert session.scalar(select(func.count()).select_from(OrderLine)) == len(one_order)
        assert any(line.modifiers for line in session.scalars(select(OrderLine)))
    corrected = [one_order[0].copy()]
    corrected[0]["menu_item_quantity"] = "7"
    write_csv(path, headers, corrected)
    import_report("grubhub", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw")
    assert totals(engine)[1:] == (1, 1, Decimal("7"))
    with Session(engine) as session:
        assert session.scalar(select(Order.id)) == stable_id


def test_invalid_rows_roll_back_sales_and_record_failure(engine, tmp_path, fixtures):
    load(engine, tmp_path, fixtures, "grubhub")
    before = totals(engine)
    headers, rows = read_csv(fixtures / "grubhub_menu_line_items.csv")
    rows[-1]["menu_item_modifiers"] = "{bad json"
    path = write_csv(tmp_path / "bad.csv", headers, rows)
    with pytest.raises(ImportFailure):
        import_report("grubhub", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw")
    assert totals(engine) == before
    with Session(engine) as session:
        failed = session.scalars(select(ImportRun).where(ImportRun.status == "failed")).all()
        assert len(failed) == 1 and failed[0].error


def test_database_write_failure_is_atomic(engine, tmp_path, fixtures):
    load(engine, tmp_path, fixtures, "doordash")
    before = totals(engine)

    def fail_line_insert(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO ORDER_LINES"):
            raise RuntimeError("simulated write failure /private/secret.csv")

    event.listen(engine, "before_cursor_execute", fail_line_insert)
    try:
        with pytest.raises(ImportFailure):
            load(engine, tmp_path, fixtures, "doordash")
    finally:
        event.remove(engine, "before_cursor_execute", fail_line_insert)
    assert totals(engine) == before
    with Session(engine) as session:
        failed = session.scalar(select(ImportRun).where(ImportRun.status == "failed"))
        assert failed is not None
        assert "/private/secret.csv" not in failed.error


@pytest.mark.parametrize("synthetic,complete", [(False, True), (True, False)])
def test_import_requires_explicit_fixture_assertions(
    engine, tmp_path, fixtures, synthetic, complete
):
    with pytest.raises((ImportFailure, ValueError)):
        import_report(
            "doordash",
            fixtures / "doordash_order_detail.csv",
            synthetic,
            complete,
            engine=engine,
            raw_storage_path=tmp_path / "raw",
        )
    assert totals(engine)[1] == 0


def test_duplicate_dd_line_id_and_conflicting_order_are_rejected(engine, tmp_path, fixtures):
    headers, rows = read_csv(fixtures / "doordash_order_detail.csv")
    path = write_csv(tmp_path / "duplicate.csv", headers, [rows[0], rows[0]])
    with pytest.raises(ImportFailure):
        import_report(
            "doordash", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw"
        )
    same_order = [r.copy() for r in rows if r["dd_order_number"] == rows[0]["dd_order_number"]]
    if len(same_order) < 2:
        other = same_order[0].copy()
        other["order_item_id"] = "new-line"
        same_order.append(other)
    same_order[-1]["subtotal"] = "999.00"
    write_csv(path, headers, same_order)
    with pytest.raises(ImportFailure):
        import_report(
            "doordash", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw"
        )
    assert totals(engine)[1] == 0


def test_cross_source_ids_and_leading_zeros(engine, tmp_path, fixtures):
    for source, filename, store_field, order_field in [
        ("doordash", "doordash_order_detail.csv", "store_id", "dd_order_number"),
        ("grubhub", "grubhub_menu_line_items.csv", "grubhub_store_id", "order_uuid"),
    ]:
        headers, rows = read_csv(fixtures / filename)
        row = rows[0].copy()
        row[store_field] = "00123"
        row[order_field] = "000-order"
        path = write_csv(tmp_path / filename, headers, [row])
        import_report(source, path, True, True, engine=engine, raw_storage_path=tmp_path / "raw")
    assert totals(engine)[:3] == (2, 2, 2)
    with Session(engine) as session:
        assert {s.external_store_id for s in session.scalars(select(SourceStore))} == {"00123"}
        assert {o.external_order_id for o in session.scalars(select(Order))} == {"000-order"}


@pytest.mark.parametrize(
    "day,clock",
    [
        ("2026-11-01", "01:30:00"),
        ("2026-05-01", "23:59:59"),
        ("2026-05-02", "00:00:00"),
    ],
)
def test_local_times_preserved_without_utc_guess(engine, tmp_path, fixtures, day, clock):
    headers, rows = read_csv(fixtures / "grubhub_menu_line_items.csv")
    row = rows[0].copy()
    row["order_date"], row["order_time_local"] = day, clock
    path = write_csv(tmp_path / "time.csv", headers, [row])
    import_report("grubhub", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw")
    with Session(engine) as session:
        order = session.scalar(select(Order))
        assert order.placed_at_local.isoformat() == day + "T" + clock
        assert order.placed_at_local.tzinfo is None
        if day == "2026-11-01":
            line = session.scalar(select(OrderLine))
            assert (
                "ambiguous" in str(order.source_details).lower() + str(line.source_details).lower()
            )


def test_nonexistent_local_time_rejected(engine, tmp_path, fixtures):
    headers, rows = read_csv(fixtures / "grubhub_menu_line_items.csv")
    row = rows[0].copy()
    row["order_date"], row["order_time_local"] = "2026-03-08", "02:30:00"
    path = write_csv(tmp_path / "nonexistent.csv", headers, [row])
    with pytest.raises(ImportFailure):
        import_report("grubhub", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw")
    assert totals(engine)[1] == 0


def test_invalid_timezone_rejected(engine, tmp_path, fixtures):
    headers, rows = read_csv(fixtures / "grubhub_menu_line_items.csv")
    row = rows[0].copy()
    row["order_time_zone"] = "Not/AZone"
    path = write_csv(tmp_path / "timezone.csv", headers, [row])
    with pytest.raises(ImportFailure):
        import_report("grubhub", path, True, True, engine=engine, raw_storage_path=tmp_path / "raw")
