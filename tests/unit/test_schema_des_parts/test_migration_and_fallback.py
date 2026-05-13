"""
Tests for migration generation, fallback entities, and relationships/indexes.
"""

import pytest
from src.core.schema_designer import (
    SchemaDesigner, SchemaDef, TableDef, ColumnDef,
)


# ============================================================
#  MIGRATION GENERATION TESTS
# ============================================================

class TestMigrationGeneration:
    """Tests for SchemaDesigner.generate_migration()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_new_table_migration(self):
        """Should generate CREATE TABLE for new tables."""
        old_schema = SchemaDef(tables=[], name="app", version=1)
        new_schema = SchemaDef(
            tables=[TableDef(
                name="orders",
                columns=[
                    ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                              primary_key=True, autoincrement=True),
                    ColumnDef(name="total", sql_type="REAL", python_type="float"),
                ],
            )],
            name="app",
        )
        migration = self.designer.generate_migration(old_schema, new_schema, version=2)
        assert "New table: orders" in migration
        assert "CREATE TABLE IF NOT EXISTS" in migration

    def test_added_column_migration(self):
        """Should generate ALTER TABLE ADD COLUMN for new columns."""
        old_table = TableDef(
            name="customer",
            columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int", primary_key=True),
                ColumnDef(name="name", sql_type="TEXT", python_type="str"),
            ],
        )
        new_table = TableDef(
            name="customer",
            columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int", primary_key=True),
                ColumnDef(name="name", sql_type="TEXT", python_type="str"),
                ColumnDef(name="phone", sql_type="TEXT", python_type="str", nullable=True),
            ],
        )
        old_schema = SchemaDef(tables=[old_table], name="app", version=1)
        new_schema = SchemaDef(tables=[new_table], name="app", version=2)
        migration = self.designer.generate_migration(old_schema, new_schema, version=2)
        assert "ALTER TABLE" in migration
        assert "ADD COLUMN" in migration
        assert "phone" in migration

    def test_dropped_table_migration(self):
        """Should generate DROP TABLE for removed tables."""
        old_schema = SchemaDef(
            tables=[TableDef(name="legacy", columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int", primary_key=True),
            ])],
            name="app",
        )
        new_schema = SchemaDef(tables=[], name="app")
        migration = self.designer.generate_migration(old_schema, new_schema, version=2)
        assert "DROP TABLE IF EXISTS" in migration
        assert "legacy" in migration

    def test_migration_includes_version_comment(self):
        """Migration should start with a version comment."""
        old_schema = SchemaDef(tables=[], name="app")
        new_schema = SchemaDef(tables=[], name="app")
        migration = self.designer.generate_migration(old_schema, new_schema, version=3)
        assert "Migration v2 -> v3" in migration


# ============================================================
#  FALLBACK ENTITY EXTRACTION TESTS
# ============================================================

class TestFallbackEntities:
    """Tests for SchemaDesigner._fallback_entities()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_detects_customer_keyword(self):
        """Should detect 'customer' keyword and create Customer entity."""
        entities = self.designer._fallback_entities("necesito un CRM para clientes")
        names = [e["name"] for e in entities]
        assert "Customer" in names

    def test_detects_product_keyword(self):
        """Should detect 'product' keyword and create Product entity."""
        entities = self.designer._fallback_entities("sistema de inventario y productos")
        names = [e["name"] for e in entities]
        assert "Product" in names

    def test_detects_invoice_keyword(self):
        """Should detect 'invoice' keyword and create Invoice entity."""
        entities = self.designer._fallback_entities("sistema de facturacion")
        names = [e["name"] for e in entities]
        assert "Invoice" in names

    def test_detects_user_keyword(self):
        """Should detect 'user' keyword and create User entity."""
        entities = self.designer._fallback_entities("auth and user management")
        names = [e["name"] for e in entities]
        assert "User" in names

    def test_default_item_entity(self):
        """Should return a generic Item entity for unrecognized descriptions."""
        entities = self.designer._fallback_entities("something completely unknown")
        names = [e["name"] for e in entities]
        assert "Item" in names


# ============================================================
#  RELATIONSHIP & INDEX TESTS
# ============================================================

class TestRelationshipsAndIndexes:
    """Tests for relationship detection and index generation."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_missing_fk_table_created(self):
        """Referenced tables not in schema should be auto-created."""
        entities = [
            {"name": "Invoice", "fields": ["customer_id:int", "total:float"]},
        ]
        schema = self.designer.design_schema("invoice system", entity_hints=entities)
        table_names = {t.name for t in schema.tables}
        assert "customer" in table_names

    def test_indexes_added_for_indexed_columns(self):
        """Columns with index=True should generate index entries."""
        entities = [
            {"name": "Order", "fields": ["status:str", "category:str"]},
        ]
        schema = self.designer.design_schema("orders", entity_hints=entities)
        order_table = next(t for t in schema.tables if t.name == "order")
        assert len(order_table.indexes) > 0

    def test_extract_db_name(self):
        """_extract_db_name should extract words from description."""
        name = self.designer._extract_db_name("Invoice Management System")
        assert name == "invoice_management"
