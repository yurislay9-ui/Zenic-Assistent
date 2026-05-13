"""
Tests for sanitize identifier, schema generation, and entity-to-table conversion.
"""

import pytest
from src.core.schema_designer import (
    SchemaDesigner, SchemaDef, TableDef, ColumnDef,
    PYTHON_TO_SQL, SQL_TO_PYTHON, _sanitize_identifier,
)


# ============================================================
#  SANITIZE IDENTIFIER TESTS
# ============================================================

class TestSanitizeIdentifier:
    """Tests for the _sanitize_identifier helper."""

    def test_valid_identifier(self):
        """Valid identifiers should be double-quoted."""
        result = _sanitize_identifier("users")
        assert result == '"users"'

    def test_valid_with_underscore(self):
        """Identifiers with underscores should be accepted."""
        result = _sanitize_identifier("user_id")
        assert result == '"user_id"'

    def test_invalid_identifier_raises(self):
        """Identifiers with special chars should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _sanitize_identifier("DROP TABLE users;")

    def test_empty_identifier_raises(self):
        """Empty identifiers should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _sanitize_identifier("")


# ============================================================
#  SCHEMA GENERATION TESTS
# ============================================================

class TestSchemaDesignerGeneration:
    """Tests for SchemaDesigner.design_schema()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_design_schema_with_entity_hints(self):
        """Should produce schema from explicit entity hints."""
        entities = [
            {"name": "Customer", "fields": ["name:str", "email:str", "age:int"]},
        ]
        schema = self.designer.design_schema("customer system", entity_hints=entities)
        assert isinstance(schema, SchemaDef)
        assert len(schema.tables) >= 1
        assert schema.tables[0].name == "customer"

    def test_design_schema_fallback_no_thinking(self):
        """Without thinking_engine, should use fallback entities."""
        schema = self.designer.design_schema("sistema de inventario y productos")
        assert isinstance(schema, SchemaDef)
        assert len(schema.tables) >= 1
        table_names = [t.name for t in schema.tables]
        assert "product" in table_names

    def test_design_schema_with_thinking_engine(self):
        """Should delegate to thinking_engine when available."""
        from unittest.mock import MagicMock
        mock_thinking = MagicMock()
        mock_plan = MagicMock()
        mock_plan.entities = [{"name": "Invoice", "fields": ["total:float", "status:str"]}]
        mock_thinking.plan_generation.return_value = mock_plan

        designer = SchemaDesigner(thinking_engine=mock_thinking)
        schema = designer.design_schema("sistema de facturacion")

        mock_thinking.plan_generation.assert_called_once_with("sistema de facturacion")
        assert len(schema.tables) >= 1
        assert schema.tables[0].name == "invoice"

    def test_design_schema_extracts_db_name(self):
        """Schema name should be extracted from description."""
        schema = self.designer.design_schema(
            "CRM system",
            entity_hints=[{"name": "Item", "fields": ["name:str"]}],
        )
        assert schema.name != "app"
        assert len(schema.name) > 0


# ============================================================
#  ENTITY-TO-TABLE CONVERSION TESTS
# ============================================================

class TestEntityToTable:
    """Tests for SchemaDesigner._entity_to_table()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_adds_default_id_column(self):
        """Every table should have an auto-increment id column."""
        table = self.designer._entity_to_table({"name": "Test", "fields": []})
        id_col = [c for c in table.columns if c.primary_key]
        assert len(id_col) == 1
        assert id_col[0].name == "id"
        assert id_col[0].autoincrement is True

    def test_adds_timestamp_columns(self):
        """Every table should have created_at and updated_at columns."""
        table = self.designer._entity_to_table({"name": "Test", "fields": []})
        col_names = [c.name for c in table.columns]
        assert "created_at" in col_names
        assert "updated_at" in col_names

    def test_detects_foreign_keys(self):
        """Fields ending with _id should be detected as foreign keys."""
        table = self.designer._entity_to_table(
            {"name": "Invoice", "fields": ["customer_id:int", "total:float"]}
        )
        fk_cols = [c for c in table.columns if c.foreign_key]
        assert len(fk_cols) == 1
        assert fk_cols[0].foreign_key == "customer.id"

    def test_unique_fields_detected(self):
        """Fields like email, sku should be marked unique."""
        table = self.designer._entity_to_table(
            {"name": "User", "fields": ["email:str", "username:str"]}
        )
        unique_cols = [c for c in table.columns if c.unique]
        unique_names = [c.name for c in unique_cols]
        assert "email" in unique_names

    def test_sql_type_mapping(self):
        """Python types should map to SQL types correctly."""
        table = self.designer._entity_to_table(
            {"name": "Test", "fields": ["count:int", "price:float", "active:bool"]}
        )
        col_map = {c.name: c for c in table.columns}
        assert col_map["count"].sql_type == "INTEGER"
        assert col_map["price"].sql_type == "REAL"
        assert col_map["active"].sql_type == "INTEGER"
