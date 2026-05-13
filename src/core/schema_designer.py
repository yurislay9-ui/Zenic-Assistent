"""
ZENIC-AGENTS - SchemaDesigner (Database Schema Generator)

Generador de esquemas de base de datos a partir de descripciones
en lenguaje natural. Diseñado para PYMEs que necesitan bases de datos
sin contratar un DBA.

Características:
  - Genera esquemas SQLite a partir de descripciones
  - Soporta relaciones (1:1, 1:N, N:M)
  - Genera SQL CREATE TABLE completo
  - Genera modelos Python (dataclasses) desde el esquema
  - Genera migraciones incrementales
  - Detecta tipos de datos automáticamente
  - Genera índices para consultas comunes

Optimizado para:
  - SQLite (sin servidor, perfecto para PYMEs)
  - FastAPI + dataclasses (sin ORM pesado)
  - Migraciones manuales (sin Alembic)
"""

from .schema_parts import *  # noqa: F401,F403
from .schema_parts import SchemaDesigner, ColumnDef, TableDef, SchemaDef  # noqa: F401

__all__ = [
    "SchemaDesigner",
    "ColumnDef", "TableDef", "SchemaDef",
    "PYTHON_TO_SQL", "SQL_TO_PYTHON", "_sanitize_identifier",
]
