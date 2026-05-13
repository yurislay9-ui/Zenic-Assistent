"""
Tests for SQL generation and Python model generation.
"""

import pytest
from src.core.schema_designer import (
    SchemaDesigner, SchemaDef, TableDef, ColumnDef,
)
from ._helpers import _make_customer_product_schema


# ============================================================
#  SQL GENERATION TESTS
# ============================================================

class TestSQLGeneration:
    """Tests for SchemaDesigner.generate_sql() and generate_init_sql()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)
        self.schema = _make_customer_product_schema()

    def test_generate_sql_creates_tables(self):
        """generate_sql should produce CREATE TABLE statements."""
        sql = self.designer.generate_sql(self.schema)
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert '"customer"' in sql
        assert '"product"' in sql

    def test_generate_sql_primary_key(self):
        """SQL should include PRIMARY KEY AUTOINCREMENT."""
        sql = self.designer.generate_sql(self.schema)
        assert "PRIMARY KEY AUTOINCREMENT" in sql

    def test_generate_sql_not_null(self):
        """SQL should include NOT NULL for non-nullable columns."""
        sql = self.designer.generate_sql(self.schema)
        assert "NOT NULL" in sql

    def test_generate_sql_unique_constraint(self):
        """SQL should include UNIQUE for unique columns."""
        sql = self.designer.generate_sql(self.schema)
        assert "UNIQUE" in sql

    def test_generate_sql_default_values(self):
        """SQL should include DEFAULT for columns with defaults."""
        sql = self.designer.generate_sql(self.schema)
        assert "CURRENT_TIMESTAMP" in sql

    def test_generate_sql_indexes(self):
        """SQL should include CREATE INDEX statements."""
        sql = self.designer.generate_sql(self.schema)
        assert "CREATE INDEX IF NOT EXISTS" in sql
        assert "idx_customer_name" in sql

    def test_generate_init_sql_includes_seed_data(self):
        """generate_init_sql should include INSERT statements for seed data."""
        sql = self.designer.generate_init_sql(self.schema)
        assert "INSERT OR IGNORE INTO" in sql

    def test_generate_init_sql_user_table_admin_seed(self):
        """User/admin tables should get an admin seed row."""
        user_table = TableDef(
            name="users",
            columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                          primary_key=True, autoincrement=True),
                ColumnDef(name="created_at", sql_type="TEXT", python_type="str",
                          default="CURRENT_TIMESTAMP"),
                ColumnDef(name="updated_at", sql_type="TEXT", python_type="str",
                          default="CURRENT_TIMESTAMP", nullable=True),
                ColumnDef(name="username", sql_type="TEXT", python_type="str"),
                ColumnDef(name="email", sql_type="TEXT", python_type="str", unique=True),
            ],
            description="Users table",
        )
        schema = SchemaDef(tables=[user_table], name="test")
        sql = self.designer.generate_init_sql(schema)
        assert "Admin" in sql
        assert "admin@company.com" in sql


# ============================================================
#  PYTHON MODEL GENERATION TESTS
# ============================================================

class TestModelGeneration:
    """Tests for SchemaDesigner.generate_models()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)
        self.schema = _make_customer_product_schema()

    def test_generate_models_produces_classes(self):
        """generate_models should produce dataclass definitions."""
        code = self.designer.generate_models(self.schema)
        assert "@dataclass" in code
        assert "class Customer:" in code
        assert "class Product:" in code

    def test_generate_models_includes_to_dict(self):
        """Models should have a to_dict() method."""
        code = self.designer.generate_models(self.schema)
        assert "def to_dict(self)" in code

    def test_generate_models_includes_from_row(self):
        """Models should have a from_row() classmethod."""
        code = self.designer.generate_models(self.schema)
        assert "def from_row(cls" in code

    def test_generate_models_includes_imports(self):
        """Models should include necessary imports."""
        code = self.designer.generate_models(self.schema)
        assert "from dataclasses import" in code
        assert "from typing import" in code
