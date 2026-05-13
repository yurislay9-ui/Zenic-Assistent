"""
ZENIC-AGENTS - Data Logic Blocks

CRUD blocks: create, read, update, delete.
Data transform block is in data_transform.py.
"""

import time
import math
import hashlib
import logging
from typing import Any, Dict

from .chain import LogicBlock, _validate_identifier

logger = logging.getLogger(__name__)


# ============================================================
#  DATA BLOCKS (4 CRUD)
# ============================================================


class CRUDCreateBlock(LogicBlock):
    """Crea un registro en la base de datos."""

    name = "crud_create"
    category = "data"
    description = "Create a new record in the database"
    inputs = ["data", "table", "fields"]
    outputs = ["result", "id", "status"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            table = data.get("table", data.get("_table", "items"))
            fields = data.get("fields", data.get("_fields", {}))

            # Use all data as fields if no explicit fields specified
            if not fields:
                fields = {k: v for k, v in data.items()
                          if not k.startswith("_") and k not in ("table", "success", "error")
                          and not isinstance(v, (list, dict)) or isinstance(v, dict)}

            # Filter out internal keys
            clean_fields = {k: v for k, v in fields.items()
                           if not k.startswith("_") and k not in ("table",)}

            db = context.get("db", None)
            if db is not None:
                try:
                    _validate_identifier(table)
                    for col in clean_fields.keys():
                        _validate_identifier(col)
                    columns = ", ".join(f'"{c}"' for c in clean_fields.keys())
                    placeholders = ", ".join(["?"] * len(clean_fields))
                    values = list(clean_fields.values())
                    cursor = db.execute(
                        f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
                        values
                    )
                    record_id = cursor.lastrowid if hasattr(cursor, 'lastrowid') else len(clean_fields)
                    db.commit() if hasattr(db, 'commit') else None
                    logger.debug(f"CRUDCreateBlock: Created record in {table}, id={record_id}")
                    return {
                        "success": True,
                        "id": record_id,
                        "table": table,
                        "fields": clean_fields,
                        "status": "created",
                    }
                except Exception as db_err:
                    logger.warning(f"CRUDCreateBlock: DB error: {db_err}")
                    return {"success": False, "error": f"Database error: {str(db_err)}"}

            # Fallback: return the data as if created
            record_id = data.get("id", hashlib.md5(str(sorted(clean_fields.items())).encode()).hexdigest()[:8])
            logger.debug(f"CRUDCreateBlock: Fallback create in {table}, id={record_id}")
            return {
                "success": True,
                "id": record_id,
                "table": table,
                "fields": clean_fields,
                "status": "created_no_db",
            }
        except Exception as e:
            return {"success": False, "error": f"CRUDCreateBlock: {str(e)}"}


class CRUDReadBlock(LogicBlock):
    """Lee registros con filtrado y paginacion."""

    name = "crud_read"
    category = "data"
    description = "Read records with filtering and pagination"
    inputs = ["table", "filters", "page", "page_size"]
    outputs = ["records", "total", "page"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            table = data.get("table", data.get("_table", "items"))
            filters = data.get("filters", {})
            page = int(data.get("page", 1))
            page_size = int(data.get("page_size", data.get("limit", 20)))
            order_by = data.get("order_by", "id DESC")

            db = context.get("db", None)
            if db is not None:
                try:
                    _validate_identifier(table)
                    where_clauses = []
                    values = []
                    for key, value in filters.items():
                        _validate_identifier(key)
                        if isinstance(value, dict):
                            op = value.get("op", "=")
                            # Only allow safe operators
                            if op not in ("=", "!=", "<", "<", ">", ">=", "LIKE", "IN"):
                                op = "="
                            val = value.get("value", value)
                            where_clauses.append(f'"{key}" {op} ?')
                            values.append(val)
                        else:
                            where_clauses.append(f'"{key}" = ?')
                            values.append(value)

                    where_str = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                    # Count
                    count_cursor = db.execute(f'SELECT COUNT(*) FROM "{table}"{where_str}', values)
                    total = count_cursor.fetchone()[0]

                    # Fetch page
                    offset = (page - 1) * page_size
                    cursor = db.execute(
                        f'SELECT * FROM "{table}"{where_str} ORDER BY {order_by} LIMIT ? OFFSET ?',
                        values + [page_size, offset]
                    )
                    rows = cursor.fetchall()
                    records = [dict(row) if hasattr(row, 'keys') else row for row in rows]

                    logger.debug(f"CRUDReadBlock: Read {len(records)} from {table}, total={total}")
                    return {
                        "success": True,
                        "records": records,
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0,
                    }
                except Exception as db_err:
                    logger.warning(f"CRUDReadBlock: DB error: {db_err}")

            # Fallback
            logger.debug(f"CRUDReadBlock: Fallback read from {table}")
            return {
                "success": True,
                "records": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "note": "No database available",
            }
        except Exception as e:
            return {"success": False, "error": f"CRUDReadBlock: {str(e)}"}


class CRUDUpdateBlock(LogicBlock):
    """Actualiza registros por ID."""

    name = "crud_update"
    category = "data"
    description = "Update records by ID"
    inputs = ["table", "id", "fields"]
    outputs = ["result", "updated_fields", "status"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            table = data.get("table", data.get("_table", "items"))
            record_id = data.get("id", data.get("record_id"))
            fields = data.get("fields", data.get("update_fields", {}))

            if not record_id:
                return {"success": False, "error": "No record ID provided for update"}

            if not fields:
                fields = {k: v for k, v in data.items()
                          if not k.startswith("_") and k not in ("table", "id", "success", "error", "record_id")
                          and isinstance(v, (str, int, float, bool))}

            if not fields:
                return {"success": False, "error": "No fields provided for update"}

            db = context.get("db", None)
            if db is not None:
                try:
                    _validate_identifier(table)
                    for k in fields.keys():
                        _validate_identifier(k)
                    set_clauses = [f'"{k}" = ?' for k in fields.keys()]
                    values = list(fields.values()) + [record_id]
                    cursor = db.execute(
                        f'UPDATE "{table}" SET {", ".join(set_clauses)} WHERE id = ?',
                        values
                    )
                    rows_affected = cursor.rowcount if hasattr(cursor, 'rowcount') else 1
                    db.commit() if hasattr(db, 'commit') else None
                    logger.debug(f"CRUDUpdateBlock: Updated {table} id={record_id}, fields={list(fields.keys())}")
                    return {
                        "success": True,
                        "id": record_id,
                        "table": table,
                        "updated_fields": list(fields.keys()),
                        "rows_affected": rows_affected,
                        "status": "updated",
                    }
                except Exception as db_err:
                    logger.warning(f"CRUDUpdateBlock: DB error: {db_err}")
                    return {"success": False, "error": f"Database error: {str(db_err)}"}

            logger.debug(f"CRUDUpdateBlock: Fallback update {table} id={record_id}")
            return {
                "success": True,
                "id": record_id,
                "table": table,
                "updated_fields": list(fields.keys()),
                "status": "updated_no_db",
            }
        except Exception as e:
            return {"success": False, "error": f"CRUDUpdateBlock: {str(e)}"}


class CRUDDeleteBlock(LogicBlock):
    """Elimina registros por ID."""

    name = "crud_delete"
    category = "data"
    description = "Delete records by ID"
    inputs = ["table", "id"]
    outputs = ["result", "status"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            table = data.get("table", data.get("_table", "items"))
            record_id = data.get("id", data.get("record_id"))
            soft_delete = data.get("soft_delete", False)

            if not record_id:
                return {"success": False, "error": "No record ID provided for deletion"}

            db = context.get("db", None)
            if db is not None:
                try:
                    _validate_identifier(table)
                    if soft_delete:
                        cursor = db.execute(
                            f'UPDATE "{table}" SET deleted_at = ? WHERE id = ?',
                            (time.strftime("%Y-%m-%d %H:%M:%S"), record_id)
                        )
                    else:
                        cursor = db.execute(f'DELETE FROM "{table}" WHERE id = ?', (record_id,))

                    rows_affected = cursor.rowcount if hasattr(cursor, 'rowcount') else 1
                    db.commit() if hasattr(db, 'commit') else None
                    logger.debug(f"CRUDDeleteBlock: Deleted from {table} id={record_id}, rows={rows_affected}")
                    return {
                        "success": True,
                        "id": record_id,
                        "table": table,
                        "rows_affected": rows_affected,
                        "status": "deleted" if not soft_delete else "soft_deleted",
                    }
                except Exception as db_err:
                    logger.warning(f"CRUDDeleteBlock: DB error: {db_err}")
                    return {"success": False, "error": f"Database error: {str(db_err)}"}

            logger.debug(f"CRUDDeleteBlock: Fallback delete from {table} id={record_id}")
            return {
                "success": True,
                "id": record_id,
                "table": table,
                "status": "deleted_no_db",
            }
        except Exception as e:
            return {"success": False, "error": f"CRUDDeleteBlock: {str(e)}"}
