"""
SchemaDesigner design and entity conversion mixin.
"""

import re
import logging
from typing import Dict, Any, List

from ._imports import (
    ColumnDef, TableDef, SchemaDef,
    PYTHON_TO_SQL, _sanitize_identifier,
    logger,
)


class DesignMixin:
    """Schema design and entity-to-table conversion methods."""

    # ================================================================
    #  MAIN ENTRY POINT
    # ================================================================

    def design_schema(self, description: str, entity_hints: List[Dict] = None) -> SchemaDef:
        """
        Diseña un esquema de BD a partir de una descripción.

        Args:
            description: Descripción en lenguaje natural
            entity_hints: Entidades pre-identificadas por ThinkingEngine

        Returns:
            SchemaDef con todas las tablas y columnas
        """
        # Step 1: Identify entities (use hints if available)
        if entity_hints:
            entities = entity_hints
        elif self._thinking:
            plan = self._thinking.plan_generation(description)
            entities = plan.entities
        else:
            entities = self._fallback_entities(description)

        # Step 2: Convert entities to table definitions
        tables = []
        for entity in entities:
            table = self._entity_to_table(entity)
            tables.append(table)

        # Step 3: Add relationships
        self._add_relationships(tables, description)

        # Step 4: Add indexes for common queries
        self._add_indexes(tables, description)

        return SchemaDef(
            tables=tables,
            name=self._extract_db_name(description),
        )

    # ================================================================
    #  ENTITY → TABLE CONVERSION
    # ================================================================

    def _entity_to_table(self, entity: Dict[str, Any]) -> TableDef:
        """Convierte una entidad a una definición de tabla."""
        name = entity.get("name", "item")
        fields = entity.get("fields", [])

        columns = [
            ColumnDef(
                name="id",
                sql_type="INTEGER",
                python_type="int",
                primary_key=True,
                autoincrement=True,
                nullable=False,
            ),
            ColumnDef(
                name="created_at",
                sql_type="TEXT",
                python_type="str",
                default="CURRENT_TIMESTAMP",
                nullable=False,
            ),
            ColumnDef(
                name="updated_at",
                sql_type="TEXT",
                python_type="str",
                default="CURRENT_TIMESTAMP",
                nullable=True,
            ),
        ]

        for f in fields:
            parts = f.split(":")
            fname = parts[0]
            ftype = parts[1] if len(parts) > 1 else "str"

            sql_type = PYTHON_TO_SQL.get(ftype, "TEXT")
            python_type = ftype if ftype in PYTHON_TO_SQL else "str"

            col = ColumnDef(
                name=fname,
                sql_type=sql_type,
                python_type=python_type,
                nullable=True,
                unique=fname in ["email", "sku", "code", "slug", "token"],
                index=fname in ["name", "status", "type", "category", "date",
                                "customer_id", "product_id", "user_id", "project_id"],
            )

            # Detect foreign keys
            if fname.endswith("_id") and fname != "id":
                ref_table = fname.replace("_id", "")
                col.foreign_key = f"{ref_table}.id"
                col.index = True

            columns.append(col)

        return TableDef(
            name=name.lower(),
            columns=columns,
            description=entity.get("description", f"Table for {name}"),
        )

    # ================================================================
    #  RELATIONSHIP DETECTION
    # ================================================================

    def _add_relationships(self, tables: List[TableDef], description: str):
        """Añade columnas de relación entre tablas."""
        table_names = {t.name for t in tables}

        # Detect 1:N relationships from foreign keys
        for table in tables:
            for col in table.columns:
                if col.foreign_key:
                    ref_table = col.foreign_key.split(".")[0]
                    if ref_table not in table_names:
                        # Reference table doesn't exist, create it
                        ref_table_def = TableDef(
                            name=ref_table,
                            columns=[
                                ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                                         primary_key=True, autoincrement=True),
                                ColumnDef(name="name", sql_type="TEXT", python_type="str", index=True),
                                ColumnDef(name="created_at", sql_type="TEXT", python_type="str",
                                         default="CURRENT_TIMESTAMP"),
                            ],
                            description=f"Referenced table for {table.name}",
                        )
                        tables.append(ref_table_def)
                        table_names.add(ref_table)

        # Detect N:M relationships from description keywords
        desc_lower = description.lower()
        nm_patterns = [
            (r"(\w+)\s*(?:y|and|con|with)\s*(\w+)", 2),  # "clientes y productos"
        ]
        # This is simplified - in production, use NLP or ThinkingEngine

    # ================================================================
    #  INDEX GENERATION
    # ================================================================

    def _add_indexes(self, tables: List[TableDef], description: str):
        """Añade índices para consultas comunes."""
        for table in tables:
            for col in table.columns:
                if col.index and not col.primary_key:
                    idx_name = f"idx_{table.name}_{col.name}"
                    if idx_name not in table.indexes:
                        table.indexes.append(idx_name)
