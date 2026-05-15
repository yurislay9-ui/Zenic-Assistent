"""
A09 InvoiceProcessor — SINGLE RESPONSIBILITY: Process invoice calculations and validations.

Deterministic invoice logic: subtotal, tax, discounts, totals, item validation.
No AI. All calculations are pure arithmetic with validation.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import InvoiceResult


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

DEFAULT_TAX_RATE = 0.16          # 16% default (common in LATAM)
MAX_DISCOUNT_PCT = 100.0         # Cap at 100%
MAX_ITEM_PRICE = 1_000_000.0     # Sanity cap per item
MAX_ITEMS = 500                  # Max items per invoice
QUANTITY_MIN = 0.0               # Min quantity (0 = free)
PRICE_MIN = 0.0                  # Min price (0 = free)


class InvoiceProcessor(BaseAgent[InvoiceResult]):
    """
    A09: Process invoice calculations and validations.

    Single Responsibility: Invoice math ONLY.
    Method: Pure arithmetic with item-level validation.
    Fallback: Empty InvoiceResult with valid=False.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A09_InvoiceProcessor", **kwargs)

    def execute(self, input_data: Any) -> InvoiceResult:
        """
        Process invoice: calculate subtotal, tax, discounts, total.

        Input (BusinessData.data dict):
            - items: list of {name, quantity, price, ...}
            - tax_rate: float (default 0.16)
            - discount: float percentage (default 0)

        Output: InvoiceResult with totals, tax, discounts, valid flag.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        items = data.get("items", [])
        tax_rate = float(data.get("tax_rate", data.get("tax", DEFAULT_TAX_RATE)))
        discount_pct = float(data.get("discount", 0))

        # ── Validation ──
        if not items:
            return InvoiceResult(
                totals={}, tax=0.0, discounts=0.0,
                valid=False, source="deterministic",
            )

        if len(items) > MAX_ITEMS:
            items = items[:MAX_ITEMS]

        # Clamp discount
        discount_pct = max(0.0, min(discount_pct, MAX_DISCOUNT_PCT))

        # ── Item-level calculations ──
        subtotal = 0.0
        processed_items = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            qty = float(item.get("quantity", 1))
            price = float(item.get("price", 0))

            # Sanity checks
            qty = max(QUANTITY_MIN, qty)
            price = max(PRICE_MIN, min(price, MAX_ITEM_PRICE))

            item_total = round(qty * price, 2)
            subtotal += item_total
            processed_items.append({
                "index": idx,
                "name": item.get("name", f"item_{idx}"),
                "quantity": qty,
                "price": price,
                "item_total": item_total,
            })

        # ── Aggregate calculations ──
        discount_amount = round(subtotal * (discount_pct / 100.0), 2) if discount_pct > 0 else 0.0
        taxable = subtotal - discount_amount
        tax_amount = round(taxable * tax_rate, 2)
        total = round(taxable + tax_amount, 2)

        # ── Build result ──
        totals = {
            "subtotal": round(subtotal, 2),
            "discount_amount": discount_amount,
            "discount_pct": discount_pct,
            "tax_amount": tax_amount,
            "tax_rate": tax_rate,
            "total": total,
            "item_count": len(processed_items),
        }

        return InvoiceResult(
            totals=totals,
            tax=tax_amount,
            discounts=discount_amount,
            valid=True,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> InvoiceResult:
        """Safe fallback: empty invoice with valid=False."""
        return InvoiceResult(
            totals={}, tax=0.0, discounts=0.0,
            valid=False, source="fallback",
        )

    # ──────────────────────────────────────────────────────────────
    # CRUD & Route-Facing Methods (in-memory store)
    # ──────────────────────────────────────────────────────────────

    def __init_store(self) -> None:
        """Lazily initialize the in-memory invoice store."""
        if not hasattr(self, "_invoices"):
            self._invoices: list[dict[str, Any]] = []
            self._next_id = 1

    def list_invoices(self, status: str = "") -> list[dict[str, Any]]:
        """Return all invoices, optionally filtered by status."""
        self.__init_store()
        if not status:
            return list(self._invoices)
        return [inv for inv in self._invoices if inv.get("status") == status]

    def create_invoice(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new invoice and return it with calculated totals."""
        self.__init_store()
        items = data.get("items", [])
        tax_rate = float(data.get("tax_rate", DEFAULT_TAX_RATE))
        discount_pct = float(data.get("discount", 0))

        # Use execute() for the math
        result = self.execute({
            "items": items,
            "tax_rate": tax_rate,
            "discount": discount_pct,
        })

        invoice = {
            "id": self._next_id,
            "client": data.get("client", ""),
            "items": items,
            "status": data.get("status", "pending"),
            "totals": result.totals if result.totals else {},
            "due_date": data.get("due_date", ""),
        }
        self._next_id += 1
        self._invoices.append(invoice)
        return invoice

    def get_overdue_invoices(self) -> list[dict[str, Any]]:
        """Return invoices that are overdue (status='overdue')."""
        self.__init_store()
        return [inv for inv in self._invoices if inv.get("status") == "overdue"]


# ──────────────────────────────────────────────────────────────
# Singleton Factory
# ──────────────────────────────────────────────────────────────

_invoice_processor_instance: InvoiceProcessor | None = None


def get_invoice_processor() -> InvoiceProcessor:
    """Return the singleton InvoiceProcessor instance."""
    global _invoice_processor_instance
    if _invoice_processor_instance is None:
        _invoice_processor_instance = InvoiceProcessor()
    return _invoice_processor_instance
