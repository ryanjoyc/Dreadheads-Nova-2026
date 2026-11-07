from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nova_backend.imports import import_report
from nova_backend.models import ImportRun, Order, OrderLine


def test_overlapping_same_source_imports_serialize(engine, tmp_path, fixtures):
    start = Barrier(2)

    def load():
        start.wait(timeout=10)
        return import_report(
            "doordash",
            fixtures / "doordash_order_detail.csv",
            True,
            True,
            engine=engine,
            raw_storage_path=tmp_path / "raw",
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(load) for _ in range(2)]
        run_ids = [future.result(timeout=30) for future in futures]
    assert len(set(run_ids)) == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 6
        assert session.scalar(select(func.count()).select_from(OrderLine)) == 10
        assert set(session.scalars(select(ImportRun.status))) == {"succeeded"}
