"""
Shared imports, constants, and dataclasses for schema_parts.
"""

import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# === SQL Type Mapping ===
PYTHON_TO_SQL = {
    "int": "INTEGER", "float": "REAL", "bool": "INTEGER",
    "str": "TEXT", "datetime": "TEXT", "date": "TEXT",
    "list": "TEXT", "dict": "TEXT", "bytes": "BLOB",
    "Decimal": "REAL",
}

SQL_TO_PYTHON = {v: k for k, v in PYTHON_TO_SQL.items()}
SQL_TO_PYTHON["INTEGER"] = "int"
SQL_TO_PYTHON["REAL"] = "float"
SQL_TO_PYTHON["TEXT"] = "str"
SQL_TO_PYTHON["BLOB"] = "bytes"


def _sanitize_identifier(name: str) -> str:
    """Sanitize SQL identifier to prevent injection. Quotes with double-quotes."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', str(name)):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return f'"{name}"'


@dataclass
class ColumnDef:
    """Definición de una columna de base de datos."""
    name: str = ""
    sql_type: str = "TEXT"
    python_type: str = "str"
    nullable: bool = True
    primary_key: bool = False
    autoincrement: bool = False
    unique: bool = False
    default: Optional[str] = None
    foreign_key: Optional[str] = None  # "table.column"
    index: bool = False


@dataclass
class TableDef:
    """Definición de una tabla de base de datos."""
    name: str = ""
    columns: List[ColumnDef] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class SchemaDef:
    """Esquema completo de base de datos."""
    tables: List[TableDef] = field(default_factory=list)
    name: str = "app"
    version: int = 1
