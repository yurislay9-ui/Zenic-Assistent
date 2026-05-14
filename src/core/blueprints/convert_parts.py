"""
Zenic-Agents Asistente - Niche Converter Helpers (Phase 5)

Extracted helper functions and mappings for the NicheConverter.
Keeps converter.py under 400 lines.
"""

from __future__ import annotations

from typing import Dict, Optional

from .types import (
    DBEntitySchema, DBFieldSchema, DBSchema,
    FieldType, MonitorHook,
)


# ──────────────────────────────────────────────────────────────
#  FIELD TYPE MAPPING
# ──────────────────────────────────────────────────────────────

NICHE_TYPE_MAP: Dict[str, FieldType] = {
    "uuid": FieldType.UUID,
    "str": FieldType.STR,
    "string": FieldType.STR,
    "text": FieldType.TEXT,
    "int": FieldType.INT,
    "integer": FieldType.INT,
    "float": FieldType.FLOAT,
    "decimal": FieldType.DECIMAL,
    "bool": FieldType.BOOL,
    "boolean": FieldType.BOOL,
    "date": FieldType.DATE,
    "datetime": FieldType.DATETIME,
    "json": FieldType.JSON,
    "blob": FieldType.BLOB,
    "bytes": FieldType.BLOB,
}

# Block → Executor type mapping
BLOCK_EXECUTOR_MAP: Dict[str, str] = {
    "email_smtp": "email",
    "whatsapp_api": "notification",
    "telegram_bot": "notification",
    "stripe_payments": "http",
    "google_sheets": "http",
    "pdf_generator": "file",
    "webhook_server": "webhook",
    "notification_manager": "notification",
    "inventory_tracker": "database",
    "report_generator": "file",
    "data_analyzer": "database",
    "crm_pipeline": "database",
    "invoice_calculator": "database",
    "task_scheduler": "schedule",
}


# ──────────────────────────────────────────────────────────────
#  TRIGGER → MONITOR MAPPING
# ──────────────────────────────────────────────────────────────

TRIGGER_MONITOR_MAP: Dict[str, str] = {
    "low_stock": "low_stock",
    "stock_bajo": "low_stock",
    "stock_low": "low_stock",
    "overdue": "overdue_invoice",
    "factura_vencida": "overdue_invoice",
    "payment_due": "overdue_invoice",
    "loan_payment_due": "overdue_invoice",
    "appointment": "tomorrow_appointment",
    "cita": "tomorrow_appointment",
    "disk": "disk_space",
    "expiry": "low_stock",
    "suspicious": "error_rate",
    "kyc": "system_health",
}


def parse_entity_fields(fields_data: list) -> list:
    """Parse entity field definitions from Niche format.

    Niche format: "field_name:type" or dict with name/type.
    """
    fields: list = []

    for field_def in fields_data:
        if isinstance(field_def, str) and ":" in field_def:
            parts = field_def.split(":", 1)
            name = parts[0].strip()
            type_str = parts[1].strip()
            field_type = NICHE_TYPE_MAP.get(type_str, FieldType.STR)
            fields.append(DBFieldSchema(
                name=name,
                field_type=field_type,
                required=(name == "id" or name.endswith("_id")),
            ))
        elif isinstance(field_def, dict):
            name = field_def.get("name", "")
            type_str = field_def.get("type", "str")
            field_type = NICHE_TYPE_MAP.get(type_str, FieldType.STR)
            fields.append(DBFieldSchema(
                name=name,
                field_type=field_type,
                required=field_def.get("required", True),
                unique=field_def.get("unique", False),
                indexed=field_def.get("indexed", False),
                default=field_def.get("default"),
                description=field_def.get("description", ""),
            ))

    return fields


def map_trigger_to_monitor(trigger_id: str, domain: str) -> Optional[str]:
    """Map a niche trigger ID to a known SNA monitor ID."""
    trigger_lower = trigger_id.lower()
    for pattern, monitor_id in TRIGGER_MONITOR_MAP.items():
        if pattern in trigger_lower:
            return monitor_id
    return None


def determine_monitor_weight(trigger_id: str) -> str:
    """Determine monitor weight from trigger keywords."""
    trigger_lower = trigger_id.lower()
    if any(kw in trigger_lower for kw in ("multi", "predict", "demand")):
        return "heavy"
    if any(kw in trigger_lower for kw in ("trend", "analysis", "projection")):
        return "medium"
    return "lightweight"


def determine_notification_channel(description: str) -> str:
    """Determine notification channel from trigger description."""
    desc_lower = description.lower()
    if any(kw in desc_lower for kw in ("crítico", "critical", "urgente")):
        return "telegram"
    return "notification"
