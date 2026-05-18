"""
ZENIC-AGENTS - Autopilot Plan Templates & Scheduling

Built-in templates for common business objectives (overdue invoices,
no-shows, stockouts, revenue) with keyword-based template matching
and a generic fallback for unknown objectives.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  PLAN TEMPLATES
# ──────────────────────────────────────────────────────────────

_PLAN_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "reduce_overdue_invoices": [
        {
            "name": "monitor_overdue",
            "description": "Monitor overdue invoice rate from billing system",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT COUNT(*) FILTER (WHERE due_date < NOW()) * 100.0 / COUNT(*) FROM invoices",
            },
            "depends_on": [],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "notify_clients",
            "description": "Send payment reminders to clients with overdue invoices",
            "action_type": "email",
            "action_config": {
                "template": "payment_reminder",
                "recipients": "overdue_clients",
            },
            "depends_on": ["monitor_overdue"],
            "estimated_impact": 0.4,
            "risk_level": "low",
        },
        {
            "name": "escalate_morosos",
            "description": "Escalate chronic non-payers to collections process",
            "action_type": "notification",
            "action_config": {
                "channel": "manager_alert",
                "template": "escalation_notice",
            },
            "depends_on": ["notify_clients"],
            "estimated_impact": 0.3,
            "risk_level": "medium",
        },
        {
            "name": "generate_report",
            "description": "Generate overdue invoices reduction report",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM overdue_report_view",
            },
            "depends_on": ["escalate_morosos"],
            "estimated_impact": 0.1,
            "risk_level": "low",
        },
    ],
    "reduce_no_shows": [
        {
            "name": "monitor_appointments",
            "description": "Monitor appointment no-show rate",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT no_show_rate FROM appointment_stats",
            },
            "depends_on": [],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "send_reminders",
            "description": "Send appointment reminders via email/SMS",
            "action_type": "notification",
            "action_config": {
                "channel": "sms_email",
                "template": "appointment_reminder",
            },
            "depends_on": ["monitor_appointments"],
            "estimated_impact": 0.4,
            "risk_level": "low",
        },
        {
            "name": "optimize_schedule",
            "description": "Optimize scheduling to minimize no-show slots",
            "action_type": "database",
            "action_config": {
                "operation": "update",
                "query": "UPDATE appointment_slots SET optimization = 'no_show_reduction'",
            },
            "depends_on": ["send_reminders"],
            "estimated_impact": 0.25,
            "risk_level": "medium",
        },
        {
            "name": "track_results",
            "description": "Track no-show reduction results over time",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM no_show_tracking",
            },
            "depends_on": ["optimize_schedule"],
            "estimated_impact": 0.15,
            "risk_level": "low",
        },
    ],
    "reduce_stockouts": [
        {
            "name": "monitor_stock",
            "description": "Monitor stock levels for products near threshold",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM inventory WHERE quantity < reorder_point",
            },
            "depends_on": [],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "auto_reorder",
            "description": "Automatically place reorders for items below threshold",
            "action_type": "notification",
            "action_config": {
                "channel": "supplier_api",
                "template": "reorder_request",
            },
            "depends_on": ["monitor_stock"],
            "estimated_impact": 0.4,
            "risk_level": "medium",
        },
        {
            "name": "notify_supplier",
            "description": "Notify supplier of pending orders",
            "action_type": "email",
            "action_config": {
                "template": "supplier_order",
                "recipients": "supplier_contacts",
            },
            "depends_on": ["auto_reorder"],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
        {
            "name": "track_deliveries",
            "description": "Track incoming deliveries and update inventory",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM purchase_orders WHERE status = 'in_transit'",
            },
            "depends_on": ["notify_supplier"],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
    ],
    "increase_revenue": [
        {
            "name": "monitor_sales",
            "description": "Monitor current sales metrics and revenue trends",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM revenue_dashboard",
            },
            "depends_on": [],
            "estimated_impact": 0.15,
            "risk_level": "low",
        },
        {
            "name": "identify_opportunities",
            "description": "Identify upselling and cross-selling opportunities",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM sales_opportunities WHERE score > 0.7",
            },
            "depends_on": ["monitor_sales"],
            "estimated_impact": 0.3,
            "risk_level": "low",
        },
        {
            "name": "create_campaigns",
            "description": "Create targeted marketing campaigns for identified opportunities",
            "action_type": "email",
            "action_config": {
                "template": "marketing_campaign",
                "recipients": "target_segment",
            },
            "depends_on": ["identify_opportunities"],
            "estimated_impact": 0.35,
            "risk_level": "medium",
        },
        {
            "name": "track_conversions",
            "description": "Track campaign conversions and revenue impact",
            "action_type": "database",
            "action_config": {
                "operation": "query",
                "query": "SELECT * FROM campaign_performance",
            },
            "depends_on": ["create_campaigns"],
            "estimated_impact": 0.2,
            "risk_level": "low",
        },
    ],
}

_GENERIC_PLAN_TEMPLATE: List[Dict[str, Any]] = [
    {
        "name": "monitor_metric",
        "description": "Monitor the objective metric from data source",
        "action_type": "database",
        "action_config": {
            "operation": "query",
        },
        "depends_on": [],
        "estimated_impact": 0.2,
        "risk_level": "low",
    },
    {
        "name": "notify_on_threshold",
        "description": "Send notification when metric crosses threshold",
        "action_type": "notification",
        "action_config": {
            "channel": "manager_alert",
            "template": "threshold_alert",
        },
        "depends_on": ["monitor_metric"],
        "estimated_impact": 0.3,
        "risk_level": "low",
    },
    {
        "name": "create_task",
        "description": "Create a corrective task based on metric analysis",
        "action_type": "database",
        "action_config": {
            "operation": "insert",
        },
        "depends_on": ["notify_on_threshold"],
        "estimated_impact": 0.3,
        "risk_level": "medium",
    },
    {
        "name": "track_progress",
        "description": "Track progress of corrective actions over time",
        "action_type": "database",
        "action_config": {
            "operation": "query",
        },
        "depends_on": ["create_task"],
        "estimated_impact": 0.2,
        "risk_level": "low",
    },
]


def _match_template(objective: Any) -> List[Dict[str, Any]]:
    """Match an objective to the best plan template.

    Tries to match based on objective name, description, tags, and
    metadata. Falls back to the generic template if no match is found.

    Args:
        objective: An Objective instance.

    Returns:
        A list of step template dictionaries.
    """
    # Build search text from objective fields
    name_lower = getattr(objective, "name", "").lower()
    desc_lower = getattr(objective, "description", "").lower()
    tags = getattr(objective, "tags", [])
    tags_lower = [t.lower() for t in tags]
    metadata = getattr(objective, "metadata", {})
    search_terms = [name_lower, desc_lower] + tags_lower

    # Keyword mapping for template matching
    keyword_map: Dict[str, str] = {
        "reduce_overdue_invoices": ["overdue", "invoice", "factura", "moroso", "vencida"],
        "reduce_no_shows": ["no_show", "no show", "ausencia", "cita", "appointment"],
        "reduce_stockouts": ["stockout", "stock", "inventario", "inventory", "agotado"],
        "increase_revenue": ["revenue", "ingreso", "sales", "venta", "revenue"],
    }

    best_match: Optional[str] = None
    best_score = 0

    for template_key, keywords in keyword_map.items():
        score = sum(1 for term in search_terms for kw in keywords if kw in term)
        if score > best_score:
            best_score = score
            best_match = template_key

    if best_match and best_score > 0:
        logger.info(
            "AutopilotPlanner: Matched template '%s' (score=%d) for objective",
            best_match, best_score,
        )
        return _PLAN_TEMPLATES[best_match]

    return _GENERIC_PLAN_TEMPLATE
