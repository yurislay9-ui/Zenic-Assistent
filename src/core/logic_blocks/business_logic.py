"""
ZENIC-AGENTS - Business Logic Blocks

Business-specific logic blocks: invoice, inventory, CRM pipeline, task scheduler.
Report, notification, and analyzer blocks are in business_analytics.py.
"""

import logging
from typing import Any, Dict

from .chain import LogicBlock

logger = logging.getLogger(__name__)


# ============================================================
#  BUSINESS LOGIC BLOCKS (4)
# ============================================================


class InvoiceCalculatorBlock(LogicBlock):
    """Calcula facturas con impuestos, descuentos y totales."""

    name = "invoice_calculator"
    category = "business_logic"
    description = "Calculate invoices with tax, discount, and total"
    inputs = ["items", "tax_rate", "discount"]
    outputs = ["subtotal", "tax_amount", "discount_amount", "total"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            items = data.get("items", [])
            tax_rate = float(data.get("tax_rate", data.get("tax", 0.16)))
            discount_pct = float(data.get("discount", data.get("discount_pct", 0)))

            if not items:
                return {"success": False, "error": "No items provided for invoice"}

            # Calculate subtotal
            subtotal = 0.0
            processed_items = []
            for item in items:
                if isinstance(item, dict):
                    qty = float(item.get("quantity", 1))
                    price = float(item.get("price", item.get("unit_price", 0)))
                    item_total = qty * price
                    subtotal += item_total
                    processed_items.append({
                        **item,
                        "item_total": round(item_total, 2),
                    })
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    qty = float(item[0])
                    price = float(item[1])
                    subtotal += qty * price

            # Calculate discount
            discount_amount = round(subtotal * (discount_pct / 100), 2) if discount_pct > 0 else 0.0

            # Calculate tax on discounted amount
            taxable = subtotal - discount_amount
            tax_amount = round(taxable * tax_rate, 2)

            # Calculate total
            total = round(taxable + tax_amount, 2)

            logger.debug(f"InvoiceCalculatorBlock: subtotal={subtotal}, tax={tax_amount}, total={total}")
            return {
                "success": True,
                "subtotal": round(subtotal, 2),
                "tax_amount": tax_amount,
                "tax_rate": tax_rate,
                "discount_amount": discount_amount,
                "discount_pct": discount_pct,
                "total": total,
                "item_count": len(items),
                "items": processed_items,
            }
        except Exception as e:
            return {"success": False, "error": f"InvoiceCalculatorBlock: {str(e)}"}


class InventoryTrackerBlock(LogicBlock):
    """Seguimiento de inventario con alertas de stock bajo."""

    name = "inventory_tracker"
    category = "business_logic"
    description = "Track stock changes and alert on low inventory"
    inputs = ["product_id", "quantity_change", "operation"]
    outputs = ["new_quantity", "alerts"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            product_id = data.get("product_id")
            quantity_change = int(data.get("quantity_change", data.get("quantity", 0)))
            operation = data.get("operation", "adjust")  # add, remove, set, adjust
            low_stock_threshold = int(data.get("low_stock_threshold", data.get("threshold", 10)))

            # Get current quantity from DB or data
            current_quantity = int(data.get("current_quantity", data.get("stock", 0)))

            db = context.get("db", None)
            if db is not None:
                try:
                    cursor = db.execute("SELECT quantity FROM inventory WHERE product_id = ?", (product_id,))  # nosemgrep: sqlalchemy-execute-raw-query
                    row = cursor.fetchone()
                    if row:
                        current_quantity = row[0] if not hasattr(row, 'keys') else row["quantity"]
                except Exception as db_err:
                    logger.debug(f"InventoryTrackerBlock: DB read failed, using data value: {db_err}")

            # Apply operation
            if operation == "add":
                new_quantity = current_quantity + quantity_change
            elif operation == "remove":
                new_quantity = max(0, current_quantity - quantity_change)
            elif operation == "set":
                new_quantity = quantity_change
            else:  # adjust (can be positive or negative)
                new_quantity = max(0, current_quantity + quantity_change)

            # Generate alerts
            alerts = []
            if new_quantity <= 0:
                alerts.append({"type": "out_of_stock", "product_id": product_id, "message": "Product is out of stock"})
            elif new_quantity <= low_stock_threshold:
                alerts.append({"type": "low_stock", "product_id": product_id, "message": f"Low stock: {new_quantity} units remaining"})

            # Update DB if available
            if db is not None:
                try:
                    db.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE inventory SET quantity = ? WHERE product_id = ?",
                        (new_quantity, product_id)
                    )
                except Exception as db_err:
                    logger.debug(f"InventoryTrackerBlock: DB update failed: {db_err}")

            logger.debug(f"InventoryTrackerBlock: {product_id} {current_quantity}->{new_quantity}, alerts={len(alerts)}")
            return {
                "success": True,
                "product_id": product_id,
                "previous_quantity": current_quantity,
                "new_quantity": new_quantity,
                "quantity_change": new_quantity - current_quantity,
                "alerts": alerts,
                "low_stock": new_quantity <= low_stock_threshold,
            }
        except Exception as e:
            return {"success": False, "error": f"InventoryTrackerBlock: {str(e)}"}


class CRMPipelineBlock(LogicBlock):
    """Mueve leads a traves de etapas de ventas."""

    name = "crm_pipeline"
    category = "business_logic"
    description = "Move leads through sales pipeline stages"
    inputs = ["lead_data", "stage", "action"]
    outputs = ["updated_lead", "next_action"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            stages = data.get("stages", [
                "new", "contacted", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"
            ])
            lead_data = data.get("lead_data", data.get("lead", {}))
            current_stage = data.get("current_stage", lead_data.get("stage", "new"))
            action = data.get("action", "advance")  # advance, regress, close_won, close_lost

            if current_stage not in stages:
                current_stage = stages[0]

            current_idx = stages.index(current_stage)
            new_stage = current_stage
            next_action = "Follow up"

            if action == "advance" and current_idx < len(stages) - 1:
                new_stage = stages[current_idx + 1]
            elif action == "regress" and current_idx > 0:
                new_stage = stages[current_idx - 1]
            elif action == "close_won":
                new_stage = "closed_won"
                next_action = "Send onboarding email"
            elif action == "close_lost":
                new_stage = "closed_lost"
                next_action = "Archive lead, schedule follow-up in 30 days"
            elif action == "set":
                target_stage = data.get("target_stage", current_stage)
                if target_stage in stages:
                    new_stage = target_stage

            # Calculate conversion probability
            stage_probabilities = {
                "new": 0.10, "contacted": 0.20, "qualified": 0.40,
                "proposal": 0.60, "negotiation": 0.80, "closed_won": 1.0, "closed_lost": 0.0,
            }
            probability = stage_probabilities.get(new_stage, 0.0)

            updated_lead = {**lead_data, "stage": new_stage, "probability": probability}

            logger.debug(f"CRMPipelineBlock: {current_stage} -> {new_stage}, prob={probability}")
            return {
                "success": True,
                "updated_lead": updated_lead,
                "previous_stage": current_stage,
                "new_stage": new_stage,
                "probability": probability,
                "next_action": next_action,
            }
        except Exception as e:
            return {"success": False, "error": f"CRMPipelineBlock: {str(e)}"}


class TaskSchedulerBlock(LogicBlock):
    """Prioriza y asigna tareas."""

    name = "task_scheduler"
    category = "business_logic"
    description = "Prioritize and assign tasks to resources"
    inputs = ["tasks", "resources"]
    outputs = ["schedule", "assignments"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            tasks = data.get("tasks", [])
            resources = data.get("resources", [])

            if not tasks:
                return {"success": False, "error": "No tasks provided"}

            # Score and sort tasks by priority
            priority_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            scored_tasks = []
            for task in tasks:
                priority = task.get("priority", "medium")
                deadline = task.get("deadline", task.get("due_date", ""))
                effort = float(task.get("effort", task.get("estimated_hours", 1)))

                # Priority score
                score = priority_map.get(priority, 2) * 25

                # Urgency bonus (simplified: tasks with deadlines get higher score)
                if deadline:
                    score += 10

                # Lower effort = easier to complete = slight bonus
                score += max(0, 10 - effort)

                scored_tasks.append({**task, "score": score})

            # Sort by score descending
            scored_tasks.sort(key=lambda t: t["score"], reverse=True)

            # Assign to resources using round-robin
            assignments = []
            schedule = []
            for idx, task in enumerate(scored_tasks):
                if resources:
                    resource = resources[idx % len(resources)]
                    assignment = {
                        "task": task.get("name", task.get("title", f"Task_{idx}")),
                        "assigned_to": resource.get("name", resource.get("id", f"Resource_{idx % len(resources)}")),
                        "priority": task.get("priority", "medium"),
                        "score": task["score"],
                        "effort": task.get("effort", 1),
                    }
                    assignments.append(assignment)
                schedule.append({
                    "order": idx + 1,
                    "task": task.get("name", f"Task_{idx}"),
                    "priority": task.get("priority", "medium"),
                    "score": task["score"],
                })

            logger.debug(f"TaskSchedulerBlock: Scheduled {len(schedule)} tasks, {len(assignments)} assignments")
            return {
                "success": True,
                "schedule": schedule,
                "assignments": assignments,
                "total_tasks": len(tasks),
                "total_resources": len(resources),
            }
        except Exception as e:
            return {"success": False, "error": f"TaskSchedulerBlock: {str(e)}"}
