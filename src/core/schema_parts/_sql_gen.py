"""
SchemaDesigner SQL generation mixin.
"""

import logging
from typing import List

from ._imports import (
    ColumnDef, TableDef, SchemaDef, _sanitize_identifier, logger,
)


class SQLGenMixin:
    """SQL generation methods for SchemaDesigner."""

    # ================================================================
    #  SQL GENERATION
    # ================================================================

    def generate_sql(self, schema: SchemaDef) -> str:
        """Genera SQL DDL completo para el esquema."""
        statements = []

        for table in schema.tables:
            # Column definitions
            col_defs = []
            for col in table.columns:
                col_sql = f"    {_sanitize_identifier(col.name)} {col.sql_type}"
                if col.primary_key:
                    col_sql += " PRIMARY KEY AUTOINCREMENT"
                if not col.nullable and not col.primary_key:
                    col_sql += " NOT NULL"
                if col.unique:
                    col_sql += " UNIQUE"
                if col.default:
                    col_sql += f" DEFAULT {col.default}"
                col_defs.append(col_sql)

            # Foreign key constraints
            fk_constraints = []
            for col in table.columns:
                if col.foreign_key:
                    fk_constraints.append(
                        f"    FOREIGN KEY ({_sanitize_identifier(col.name)}) REFERENCES {_sanitize_identifier(col.foreign_key)}"
                    )

            all_defs = col_defs + fk_constraints
            create_sql = f"CREATE TABLE IF NOT EXISTS {_sanitize_identifier(table.name)} (\n" + ",\n".join(all_defs) + "\n);"
            statements.append(create_sql)

            # Index statements
            for col in table.columns:
                if col.index and not col.primary_key:
                    idx_name = f"idx_{table.name}_{col.name}"
                    statements.append(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} ON {_sanitize_identifier(table.name)}({_sanitize_identifier(col.name)});"
                    )

        return "\n\n".join(statements)

    def generate_init_sql(self, schema: SchemaDef) -> str:
        """Genera SQL completo de inicialización con datos de ejemplo."""
        sql = self.generate_sql(schema)

        # Add seed data for each table
        for table in schema.tables:
            seed = self._generate_seed_data(table)
            if seed:
                sql += f"\n\n{seed}"

        return sql

    def _generate_seed_data(self, table: TableDef) -> str:
        """Genera datos de ejemplo para una tabla."""
        non_id_cols = [c for c in table.columns if not c.primary_key and not c.autoincrement
                       and c.name not in ("created_at", "updated_at")]
        if not non_id_cols:
            return ""

        is_user_table = table.name in ("user", "users", "admin")

        if is_user_table:
            return self._generate_user_seed(table, non_id_cols)

        # Generate 2 sample rows for non-user tables
        return self._generate_sample_rows(table, non_id_cols)

    def _generate_user_seed(self, table: TableDef, non_id_cols: List[ColumnDef]) -> str:
        """Generate seed data for user/admin tables."""
        row_vals = []
        for col in non_id_cols:
            if col.name in ("name", "username", "display_name"):
                row_vals.append("'Admin'")
            elif col.name in ("email", "mail"):
                row_vals.append("'admin@company.com'")
            elif col.python_type == "int":
                row_vals.append("1")
            elif col.python_type == "float":
                row_vals.append("0.0")
            elif col.python_type == "bool":
                row_vals.append("1")
            else:
                row_vals.append(f"'Sample {col.name}'")

        # Build column list from actual table columns
        has_id_col = any(c.primary_key for c in table.columns)
        cols = []
        if has_id_col:
            cols.append("id")
        cols += [c.name for c in non_id_cols]
        if any(c.name == "created_at" for c in table.columns):
            cols.append("created_at")
        if any(c.name == "updated_at" for c in table.columns):
            cols.append("updated_at")

        # Build values list matching the column order
        vals = []
        if has_id_col:
            vals.append("1")
        vals += row_vals
        if any(c.name == "created_at" for c in table.columns):
            vals.append("datetime('now')")
        if any(c.name == "updated_at" for c in table.columns):
            vals.append("datetime('now')")

        return f"""INSERT OR IGNORE INTO {_sanitize_identifier(table.name)} ({', '.join(_sanitize_identifier(c) for c in cols)}) VALUES
    ({', '.join(vals)});"""

    def _generate_sample_rows(self, table: TableDef, non_id_cols: List[ColumnDef]) -> str:
        """Generate 2 sample rows for non-user tables."""
        values = []
        cols = []
        for i in range(1, 3):
            row_vals = []
            for col in non_id_cols:
                if col.python_type == "int":
                    row_vals.append(str(i * 10))
                elif col.python_type == "float":
                    row_vals.append(f"{i * 100.0:.2f}")
                elif col.python_type == "bool":
                    row_vals.append("1")
                else:
                    row_vals.append(f"'Sample {col.name} {i}'")

            # Build column and value lists dynamically
            row_cols = []
            row_vals_full = []
            has_id_col = any(c.primary_key for c in table.columns)
            if has_id_col:
                row_cols.append("id")
                row_vals_full.append(str(i))
            row_cols += [c.name for c in non_id_cols]
            row_vals_full += row_vals
            if any(c.name == "created_at" for c in table.columns):
                row_cols.append("created_at")
                row_vals_full.append("datetime('now')")
            if any(c.name == "updated_at" for c in table.columns):
                row_cols.append("updated_at")
                row_vals_full.append("datetime('now')")

            values.append(f"    ({', '.join(row_vals_full)})")
            if i == 1:
                cols = row_cols

        return f"""INSERT OR IGNORE INTO {_sanitize_identifier(table.name)} ({', '.join(_sanitize_identifier(c) for c in cols)}) VALUES
{',\n'.join(values)};"""
