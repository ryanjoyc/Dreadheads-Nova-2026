"""Create the sales storage and import audit tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_sales"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_stores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_store_id", sa.Text(), nullable=False),
        sa.Column("store_name", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text()),
        sa.Column("source_details", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_store_id", name="uq_source_store"),
        sa.CheckConstraint("source IN ('doordash', 'grubhub')", name="ck_store_source"),
    )
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("report_version", sa.Integer()),
        sa.Column("requested_columns", postgresql.JSONB(), nullable=False),
        sa.Column("date_start", sa.Date()),
        sa.Column("date_end", sa.Date()),
        sa.Column("provider_report_id", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("raw_file_reference", sa.Text()),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("source IN ('doordash', 'grubhub')", name="ck_import_source"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_import_status"),
    )
    op.create_index("ix_import_runs_status", "import_runs", ["status"])
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_store_id", sa.Uuid(), nullable=False),
        sa.Column("external_order_id", sa.Text(), nullable=False),
        sa.Column("order_number", sa.Text()),
        sa.Column("placed_at_local", sa.DateTime(), nullable=False),
        sa.Column("source_timezone", sa.Text(), nullable=False),
        sa.Column("fulfillment", sa.Text()),
        sa.Column("subtotal", sa.Numeric(18, 6)),
        sa.Column("source_details", postgresql.JSONB(), nullable=False),
        sa.Column("last_import_run_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["source_store_id"], ["source_stores.id"]),
        sa.ForeignKeyConstraint(["last_import_run_id"], ["import_runs.id"]),
        sa.UniqueConstraint("source_store_id", "external_order_id", name="uq_store_order"),
        sa.CheckConstraint(
            "fulfillment IS NULL OR fulfillment IN ('pickup', 'delivery')",
            name="ck_order_fulfillment",
        ),
        sa.CheckConstraint("subtotal IS NULL OR subtotal >= 0", name="ck_order_subtotal"),
    )
    for column in ("source_store_id", "placed_at_local", "last_import_run_id"):
        op.create_index(f"ix_orders_{column}", "orders", [column])
    op.create_table(
        "order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("external_line_id", sa.Text()),
        sa.Column("external_item_id", sa.Text(), nullable=False),
        sa.Column("item_name", sa.Text(), nullable=False),
        sa.Column("category_name", sa.Text()),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6)),
        sa.Column("modifiers", postgresql.JSONB()),
        sa.Column("source_details", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("order_id", "external_line_id", name="uq_order_external_line"),
        sa.CheckConstraint("quantity > 0", name="ck_line_quantity"),
        sa.CheckConstraint("unit_price IS NULL OR unit_price >= 0", name="ck_line_price"),
    )
    for column in ("order_id", "external_item_id"):
        op.create_index(f"ix_order_lines_{column}", "order_lines", [column])


def downgrade():
    op.drop_table("order_lines")
    op.drop_table("orders")
    op.drop_table("import_runs")
    op.drop_table("source_stores")
