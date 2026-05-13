"""Shared helper for schema designer tests."""

import pytest
from src.core.schema_designer import (
    SchemaDesigner, SchemaDef, TableDef, ColumnDef,
    PYTHON_TO_SQL, SQL_TO_PYTHON, _sanitize_identifier,
)


def _make_customer_product_schema():
    """Create a sample schema with Customer and Product tables."""
    customer_table = TableDef(
        name="customer",
        columns=[
            ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                      primary_key=True, autoincrement=True, nullable=False),
            ColumnDef(name="created_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=False),
            ColumnDef(name="updated_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=True),
            ColumnDef(name="name", sql_type="TEXT", python_type="str",
                      nullable=True, index=True),
            ColumnDef(name="email", sql_type="TEXT", python_type="str",
                      nullable=True, unique=True),
        ],
        indexes=["idx_customer_name"],
        description="Table for Customer",
    )
    product_table = TableDef(
        name="product",
        columns=[
            ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                      primary_key=True, autoincrement=True, nullable=False),
            ColumnDef(name="created_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=False),
            ColumnDef(name="updated_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=True),
            ColumnDef(name="name", sql_type="TEXT", python_type="str",
                      nullable=True, index=True),
            ColumnDef(name="sku", sql_type="TEXT", python_type="str",
                      nullable=True, unique=True),
            ColumnDef(name="price", sql_type="REAL", python_type="float",
                      nullable=True),
        ],
        indexes=["idx_product_name"],
        description="Table for Product",
    )
    return SchemaDef(tables=[customer_table, product_table], name="test_db", version=1)
