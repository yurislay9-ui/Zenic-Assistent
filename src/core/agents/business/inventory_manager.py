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

    # ──────────────────────────────────────────────────────────────
    # CRUD & Route-Facing Methods (in-memory store)
    # ──────────────────────────────────────────────────────────────

    def __init_store(self) -> None:
        """Lazily initialize the in-memory product store."""
        if not hasattr(self, "_products"):
            self._products: list[dict[str, Any]] = []
            self._next_id = 1

    def list_products(self) -> list[dict[str, Any]]:
        """Return all products."""
        self.__init_store()
        return list(self._products)

    def get_stats(self) -> dict[str, Any]:
        """Return inventory statistics."""
        self.__init_store()
        low_stock = [p for p in self._products if p.get("quantity", 0) <= p.get("low_stock_threshold", DEFAULT_LOW_STOCK_THRESHOLD)]
        return {
            "total_products": len(self._products),
            "low_stock_count": len(low_stock),
            "total_value": sum(p.get("quantity", 0) * p.get("price", 0) for p in self._products),
        }

    def add_product(self, data: dict[str, Any]) -> dict[str, Any]:
        """Add a new product and return it with an assigned ID."""
        self.__init_store()
        product = {
            "id": self._next_id,
            "name": data.get("name", ""),
            "sku": data.get("sku", ""),
            "quantity": int(data.get("quantity", 0)),
            "price": float(data.get("price", 0)),
            "low_stock_threshold": int(data.get("low_stock_threshold", DEFAULT_LOW_STOCK_THRESHOLD)),
            "category": data.get("category", ""),
        }
        self._next_id += 1
        self._products.append(product)
        return product

    def update_product(self, product_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing product. Returns updated product or None."""
        self.__init_store()
        for i, p in enumerate(self._products):
            if str(p.get("id")) == str(product_id):
                self._products[i].update(data)
                self._products[i]["id"] = p["id"]  # preserve ID
                return self._products[i]
        return None

    def delete_product(self, product_id: str) -> bool:
        """Delete a product by ID. Returns True if deleted."""
        self.__init_store()
        before = len(self._products)
        self._products = [p for p in self._products if str(p.get("id")) != str(product_id)]
        return len(self._products) < before

    def get_low_stock_products(self) -> list[dict[str, Any]]:
        """Return products at or below their low-stock threshold."""
        self.__init_store()
        return [
            p for p in self._products
            if p.get("quantity", 0) <= p.get("low_stock_threshold", DEFAULT_LOW_STOCK_THRESHOLD)
        ]


# ──────────────────────────────────────────────────────────────
# Singleton Factory
# ──────────────────────────────────────────────────────────────

_inventory_manager_instance: InventoryManager | None = None


def get_inventory_manager() -> InventoryManager:
    """Return the singleton InventoryManager instance."""
    global _inventory_manager_instance
    if _inventory_manager_instance is None:
        _inventory_manager_instance = InventoryManager()
    return _inventory_manager_instance
