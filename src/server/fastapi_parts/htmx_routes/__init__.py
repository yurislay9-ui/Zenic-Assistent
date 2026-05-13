"""HTMX routes package for Zenic-Agents Asistente (Phase 7 + Phase D2 + Enhanced)."""
from .dashboard_routes import register_dashboard_routes
from .sna_routes import register_sna_htmx_routes
from .audit_routes import register_audit_htmx_routes
from .billing_routes import register_billing_routes
from .module_routes import register_module_routes
from .system_routes import register_system_routes
from .roi_routes import register_roi_routes
from .inventory_routes import register_inventory_routes
from .crm_routes import register_crm_routes
from .onboarding_routes import register_onboarding_routes

__all__ = [
    "register_dashboard_routes",
    "register_sna_htmx_routes",
    "register_audit_htmx_routes",
    "register_billing_routes",
    "register_module_routes",
    "register_system_routes",
    "register_roi_routes",
    "register_inventory_routes",
    "register_crm_routes",
    "register_onboarding_routes",
]
