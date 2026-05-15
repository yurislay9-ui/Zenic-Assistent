"""
A16 OperationRouter — SINGLE RESPONSIBILITY: Route business operations to the correct processor agent.

Deterministic routing: maps operation type to target agent name with input transformation.
No AI. Pure lookup-table routing.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import RoutedOperation


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

# Operation type → target agent mapping
OPERATION_ROUTES = {
    "invoice": "A09_InvoiceProcessor",
    "inventory": "A10_InventoryManager",
    "crm": "A11_CRMPipeline",
    "task": "A12_TaskScheduler",
    "report": "A13_ReportGenerator",
    "notification": "A14_NotificationDispatcher",
    "analytics": "A15_DataAnalyzer",
}

# Alias mapping (common synonyms)
OPERATION_ALIASES = {
    "factura": "invoice",
    "facturacion": "invoice",
    "billing": "invoice",
    "inventario": "inventory",
    "stock": "inventory",
    "ventas": "crm",
    "sales": "crm",
    "leads": "crm",
    "tareas": "task",
    "tasks": "task",
    "scheduling": "task",
    "reporte": "report",
    "informe": "report",
    "notificacion": "notification",
    "notify": "notification",
    "alert": "notification",
    "analisis": "analytics",
    "analysis": "analytics",
    "stats": "analytics",
    "statistics": "analytics",
    "custom": "analytics",  # Custom → analytics (routed through OPERATION_ROUTES)
}

# Default route when operation type is unknown
DEFAULT_ROUTE = "A15_DataAnalyzer"


class OperationRouter(BaseAgent[RoutedOperation]):
    """
    A16: Route business operations to the correct processor agent.

    Single Responsibility: Operation routing ONLY.
    Method: Deterministic lookup table with alias resolution.
    Fallback: Route to DataAnalyzer (safest default).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A16_OperationRouter", **kwargs)

    def execute(self, input_data: Any) -> RoutedOperation:
        """
        Route operation: resolve type to target agent with transformed input.

        Input (BusinessData):
            - type: str (invoice|inventory|crm|task|report|notification|analytics|custom)
            - data: dict (payload)
            - context: dict (additional context)
            - description: str

        Output: RoutedOperation with target_agent and transformed_input.
        """
        # Extract operation type
        if hasattr(input_data, "type"):
            op_type = str(input_data.type).lower()
            data = getattr(input_data, "data", {})
            context = getattr(input_data, "context", {})
            description = getattr(input_data, "description", "")
        elif isinstance(input_data, dict):
            op_type = str(input_data.get("type", "")).lower()
            data = input_data.get("data", {})
            context = input_data.get("context", {})
            description = input_data.get("description", "")
        else:
            op_type = ""
            data = {}
            context = {}
            description = str(input_data)

        # ── Resolve operation type ──
        # Step 1: Check direct routes
        target_agent = OPERATION_ROUTES.get(op_type)

        # Step 2: Check aliases
        if not target_agent:
            canonical = OPERATION_ALIASES.get(op_type)
            if canonical:
                if canonical in OPERATION_ROUTES:
                    target_agent = OPERATION_ROUTES[canonical]
                else:
                    target_agent = canonical  # Already an agent name (e.g., custom)

        # Step 3: Default route
        if not target_agent:
            target_agent = DEFAULT_ROUTE

        # ── Transform input for target agent ──
        transformed_input = {
            "type": op_type,
            "data": data,
            "context": context,
            "description": description,
            "routed_from": "A16_OperationRouter",
        }

        return RoutedOperation(
            target_agent=target_agent,
            transformed_input=transformed_input,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> RoutedOperation:
        """Safe fallback: route to default DataAnalyzer."""
        return RoutedOperation(
            target_agent=DEFAULT_ROUTE,
            transformed_input={"data": {}, "context": {}, "description": ""},
            source="fallback",
        )
