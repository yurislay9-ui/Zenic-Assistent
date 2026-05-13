"""
SchemaDesigner sub-package — Database schema generator.
"""

from ._imports import (
    PYTHON_TO_SQL, SQL_TO_PYTHON, _sanitize_identifier,
    ColumnDef, TableDef, SchemaDef,
)
from ._design import DesignMixin
from ._sql_gen import SQLGenMixin
from ._python_gen import PythonGenMixin
from ._fallbacks import FallbackMixin
from ._designer import SchemaDesigner

__all__ = [
    "PYTHON_TO_SQL", "SQL_TO_PYTHON", "_sanitize_identifier",
    "ColumnDef", "TableDef", "SchemaDef",
    "DesignMixin", "SQLGenMixin", "PythonGenMixin", "FallbackMixin",
    "SchemaDesigner",
]
