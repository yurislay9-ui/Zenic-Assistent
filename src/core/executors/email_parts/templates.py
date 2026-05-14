"""
ZENIC-AGENTS - Email Template Engine (Phase 3)

Template engine for generating structured email content.
Provides built-in templates for common business scenarios
and supports custom template registration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from string import Template as StringTemplate
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class EmailTemplate:
    """A structured email template."""
    name: str
    subject_template: str
    body_template: str                      # Plain text template
    html_template: str = ""                 # HTML template (optional)
    category: str = "general"               # general, financial, alert, notification
    required_variables: List[str] = field(default_factory=list)
    has_attachments: bool = False
    description: str = ""


# ──────────────────────────────────────────────────────────────
#  BUILT-IN TEMPLATES
# ──────────────────────────────────────────────────────────────

BUILTIN_TEMPLATES: Dict[str, EmailTemplate] = {
    "invoice": EmailTemplate(
        name="invoice",
        subject_template="Invoice #$invoice_number from $company_name",
        body_template=(
            "Dear $customer_name,\n\n"
            "Please find below your invoice:\n\n"
            "Invoice #: $invoice_number\n"
            "Date: $invoice_date\n"
            "Due Date: $due_date\n\n"
            "Items:\n$item_lines\n\n"
            "Subtotal: $subtotal\n"
            "Tax ($tax_rate%): $tax_amount\n"
            "Total: $total\n\n"
            "Payment terms: $payment_terms\n\n"
            "Thank you for your business.\n"
            "$company_name"
        ),
        html_template=(
            "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
            "<h2>Invoice #$invoice_number</h2>"
            "<p>Dear $customer_name,</p>"
            "<table style='width:100%; border-collapse:collapse;'>"
            "<tr><th style='border:1px solid #ddd;padding:8px;'>Item</th>"
            "<th style='border:1px solid #ddd;padding:8px;'>Qty</th>"
            "<th style='border:1px solid #ddd;padding:8px;'>Price</th>"
            "<th style='border:1px solid #ddd;padding:8px;'>Total</th></tr>"
            "$html_item_rows"
            "</table>"
            "<p><strong>Subtotal:</strong> $subtotal</p>"
            "<p><strong>Tax:</strong> $tax_amount</p>"
            "<p><strong>Total:</strong> $total</p>"
            "<p>Due date: $due_date</p>"
            "</div>"
        ),
        category="financial",
        required_variables=["invoice_number", "customer_name", "total"],
        has_attachments=True,
        description="Invoice email template with itemized details",
    ),
    "reminder": EmailTemplate(
        name="reminder",
        subject_template="Reminder: $reminder_subject",
        body_template=(
            "Dear $recipient_name,\n\n"
            "This is a reminder about: $reminder_subject\n\n"
            "Details: $reminder_details\n"
            "Due date: $due_date\n\n"
            "Please take action before the due date.\n\n"
            "Best regards,\n$company_name"
        ),
        html_template=(
            "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
            "<h2>Reminder: $reminder_subject</h2>"
            "<p>Dear $recipient_name,</p>"
            "<p>$reminder_details</p>"
            "<p><strong>Due date:</strong> $due_date</p>"
            "</div>"
        ),
        category="notification",
        required_variables=["reminder_subject", "recipient_name"],
        description="General reminder email template",
    ),
    "alert": EmailTemplate(
        name="alert",
        subject_template="ALERT: $alert_title",
        body_template=(
            "ALERT NOTIFICATION\n"
            "==================\n\n"
            "Alert: $alert_title\n"
            "Severity: $severity\n"
            "Time: $alert_time\n\n"
            "Description: $alert_description\n\n"
            "Action required: $action_required\n\n"
            "This is an automated alert from $system_name."
        ),
        html_template=(
            "<div style='font-family: Arial, sans-serif; max-width: 600px; "
            "border-left: 4px solid #e74c3c; padding-left: 16px;'>"
            "<h2 style='color: #e74c3c;'>ALERT: $alert_title</h2>"
            "<p><strong>Severity:</strong> $severity</p>"
            "<p><strong>Time:</strong> $alert_time</p>"
            "<p>$alert_description</p>"
            "<p><strong>Action required:</strong> $action_required</p>"
            "</div>"
        ),
        category="alert",
        required_variables=["alert_title"],
        description="Critical alert notification email template",
    ),
    "welcome": EmailTemplate(
        name="welcome",
        subject_template="Welcome to $service_name!",
        body_template=(
            "Dear $user_name,\n\n"
            "Welcome to $service_name!\n\n"
            "Your account has been created successfully.\n"
            "You can now access all features of our platform.\n\n"
            "Getting started:\n"
            "1. Complete your profile\n"
            "2. Configure your preferences\n"
            "3. Explore the dashboard\n\n"
            "If you need help, contact us at $support_email\n\n"
            "Best regards,\nThe $service_name Team"
        ),
        html_template=(
            "<div style='font-family: Arial, sans-serif; max-width: 600px;'>"
            "<h2>Welcome to $service_name!</h2>"
            "<p>Dear $user_name,</p>"
            "<p>Your account has been created successfully.</p>"
            "<p>If you need help, contact us at $support_email</p>"
            "</div>"
        ),
        category="notification",
        required_variables=["user_name", "service_name"],
        description="Welcome email for new users",
    ),
    "low_stock": EmailTemplate(
        name="low_stock",
        subject_template="Low Stock Alert: $product_name",
        body_template=(
            "LOW STOCK ALERT\n"
            "===============\n\n"
            "Product: $product_name\n"
            "SKU: $sku\n"
            "Current Stock: $current_stock\n"
            "Minimum Threshold: $min_threshold\n\n"
            "This product is below the minimum stock level.\n"
            "Reorder quantity suggested: $reorder_qty\n\n"
            "Supplier: $supplier_name\n"
            "Supplier Contact: $supplier_contact\n\n"
            "Please review and place a reorder if needed."
        ),
        category="alert",
        required_variables=["product_name", "current_stock", "min_threshold"],
        description="Low stock alert for inventory management",
    ),
}


# ──────────────────────────────────────────────────────────────
#  TEMPLATE ENGINE
# ──────────────────────────────────────────────────────────────

class EmailTemplateEngine:
    """Engine for rendering email templates with variable substitution.

    Features:
      - Built-in templates for common business scenarios
      - Custom template registration
      - Variable validation (required variables checked)
      - Safe substitution (missing variables get placeholder)
      - HTML and plain text rendering
    """

    def __init__(self) -> None:
        self._templates: Dict[str, EmailTemplate] = dict(BUILTIN_TEMPLATES)
        self._custom_count: int = 0

    def register_template(self, template: EmailTemplate) -> None:
        """Register a custom email template."""
        self._templates[template.name] = template
        self._custom_count += 1
        logger.info(f"EmailTemplateEngine: Registered template '{template.name}'")

    def get_template(self, name: str) -> Optional[EmailTemplate]:
        """Get a template by name."""
        return self._templates.get(name)

    def list_templates(self) -> List[str]:
        """List all available template names."""
        return list(self._templates.keys())

    def render(
        self,
        template_name: str,
        variables: Dict[str, Any],
        fallback_to_raw: bool = True,
    ) -> Dict[str, str]:
        """Render a template with the given variables.

        Returns:
            Dict with 'subject', 'body', 'html' keys.
        """
        template = self._templates.get(template_name)
        if not template:
            if fallback_to_raw:
                logger.warning(
                    f"EmailTemplateEngine: Template '{template_name}' not found, "
                    f"using raw variables"
                )
                return {
                    "subject": str(variables.get("subject", template_name)),
                    "body": str(variables.get("body", "")),
                    "html": str(variables.get("html", "")),
                }
            raise ValueError(f"Template '{template_name}' not found")

        # Validate required variables
        missing = [
            v for v in template.required_variables
            if v not in variables and f"${v}" not in str(variables)
        ]
        if missing:
            logger.warning(
                f"EmailTemplateEngine: Missing variables for '{template_name}': {missing}"
            )

        # Render with safe substitution
        safe_vars = self._prepare_variables(variables)

        subject = self._safe_substitute(template.subject_template, safe_vars)
        body = self._safe_substitute(template.body_template, safe_vars)
        html = ""
        if template.html_template:
            html = self._safe_substitute(template.html_template, safe_vars)

        return {"subject": subject, "body": body, "html": html}

    def render_from_config(self, config: Dict[str, Any]) -> Dict[str, str]:
        """Render from an executor config dict.

        Config should have 'template' (name) and 'template_vars' (dict).
        Falls back to raw subject/body/html if no template specified.
        """
        template_name = config.get("template", "")
        template_vars = config.get("template_vars", {})

        if template_name:
            return self.render(template_name, template_vars)

        # No template — use raw values from config
        return {
            "subject": config.get("subject", "No Subject"),
            "body": config.get("body", ""),
            "html": config.get("html", ""),
        }

    @property
    def stats(self) -> Dict[str, Any]:
        """Get template engine statistics."""
        return {
            "total_templates": len(self._templates),
            "builtin_templates": len(BUILTIN_TEMPLATES),
            "custom_templates": self._custom_count,
            "template_names": list(self._templates.keys()),
        }

    # ── Private methods ──────────────────────────────────────

    @staticmethod
    def _prepare_variables(variables: Dict[str, Any]) -> Dict[str, str]:
        """Convert all variable values to strings for substitution."""
        return {k: str(v) for k, v in variables.items()}

    @staticmethod
    def _safe_substitute(template_str: str, variables: Dict[str, str]) -> str:
        """Safe substitution that leaves unknown $variables as-is."""
        tmpl = StringTemplate(template_str)
        return tmpl.safe_substitute(variables)
