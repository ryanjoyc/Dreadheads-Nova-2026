"""Integration tests are destructive only inside the dedicated test database."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture(scope="session")
def database_url():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value or (make_url(value).database, make_url(value).host) != (
        "nova_sales_test",
        "db-test",
    ):
        pytest.fail("Set TEST_DATABASE_URL to the disposable nova_sales_test database")
    if value != os.environ.get("DATABASE_URL"):
        pytest.fail("DATABASE_URL and TEST_DATABASE_URL must match for integration tests")
    return value


@pytest.fixture(scope="session")
def engine(database_url):
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(engine):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE order_lines, orders, source_stores, import_runs CASCADE"))
    yield


@pytest.fixture
def fixtures():
    return Path(__file__).resolve().parents[1] / "fixtures"
