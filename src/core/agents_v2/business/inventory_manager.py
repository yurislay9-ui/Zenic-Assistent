"""
A10 InventoryManager — SINGLE RESPONSIBILITY: Track inventory levels, reorder points, stock alerts.

Deterministic inventory logic: stock adjustments, low-stock alerts, reorder suggestions.
No AI. Pure arithmetic with threshold checks.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import InventoryResult


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

DEFAULT_LOW_STOCK_THRESHOLD = 10
VALID_OPERATIONS = frozenset({"add", "remove", "set", "adjust"})


class InventoryManager(BaseAgent[InventoryResult]):
    """
    A10: Track inventory levels, reorder points, stock alerts.

    Single Responsibility: Inventory stock management ONLY.
    Method: Deterministic stock calculation with threshold alerts.
    Fallback: Empty InventoryResult with no levels.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A10_InventoryManager", **kwargs)

    def execute(self, input_data: Any) -> InventoryResult:
        """
        Track inventory: adjust quantities, detect low-stock, suggest reorders.

        Input (BusinessData.data dict):
            - product_id: str
            - quantity_change / quantity: int
            - operation: "add"|"remove"|"set"|"adjust"
            - current_quantity / stock: int
            - low_stock_threshold: int (default 10)

        Output: InventoryResult with levels, alerts, reorder list.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        product_id = str(data.get("product_id", "unknown"))
        quantity_change = int(data.get("quantity_change", data.get("quantity", 0)))
        operation = str(data.get("operation", "adjust")).lower()
        current_qty = int(data.get("current_quantity", data.get("stock", 0)))
        threshold = int(data.get("low_stock_threshold", DEFAULT_LOW_STOCK_THRESHOLD))

        # ── Compute new quantity ──
        if operation == "add":
            new_qty = current_qty + quantity_change
        elif operation == "remove":
            new_qty = max(0, current_qty - quantity_change)
        elif operation == "set":
            new_qty = max(0, quantity_change)
        else:  # "adjust"
            new_qty = max(0, current_qty + quantity_change)

        # ── Alerts ──
        alerts: list[str] = []
        reorder: list[str] = []

        if new_qty <= 0:
            alerts.append(f"OUT_OF_STOCK:{product_id}:qty=0")
            reorder.append(product_id)
        elif new_qty <= threshold:
            alerts.append(f"LOW_STOCK:{product_id}:qty={new_qty}:threshold={threshold}")
            reorder.append(product_id)

        # ── Build result ──
        levels = {
            product_id: new_qty,
            f"{product_id}_previous": current_qty,
            f"{product_id}_change": new_qty - current_qty,
            f"{product_id}_low_stock": new_qty <= threshold,
        }

        return InventoryResult(
            levels=levels,
            alerts=alerts,
            reorder=reorder,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> InventoryResult:
        """Safe fallback: empty inventory result."""
        return InventoryResult(
            levels={}, alerts=[], reorder=[],
            source="fallback",
        )
