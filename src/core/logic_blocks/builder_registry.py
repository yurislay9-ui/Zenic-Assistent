"""
ZENIC-AGENTS - Builder Registry Helpers

Block registry, keyword map, code generation helpers extracted from LogicBuilder.
These functions support the LogicBuilder by providing keyword mapping,
template block resolution, and inline code generation for _process().
"""

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
#  KEYWORD MAP
# ============================================================


def build_keyword_map() -> Dict[str, List[str]]:
    """Construye mapa de keywords -> block names para sugerencias.

    Returns:
        Dictionary mapping keywords to lists of block names
    """
    return {
        # Flow keywords
        "if": ["conditional"], "else": ["conditional"], "branch": ["conditional"],
        "conditional": ["conditional"], "condition": ["conditional"],
        "loop": ["loop"], "iterate": ["loop"], "each": ["loop"], "foreach": ["loop"],
        "parallel": ["parallel"], "concurrent": ["parallel"], "simultaneous": ["parallel"],
        "switch": ["switch"], "case": ["switch"], "multi": ["switch"],
        "try": ["try_catch"], "catch": ["try_catch"], "error": ["try_catch"], "exception": ["try_catch"],
        # Validation keywords
        "required": ["validate_required"], "mandatory": ["validate_required"],
        "validate": ["validate_required", "validate_types", "validate_ranges"],
        "type": ["validate_types"], "schema": ["validate_types"],
        "range": ["validate_ranges"], "min": ["validate_ranges"], "max": ["validate_ranges"],
        "unique": ["validate_unique"], "duplicate": ["validate_unique"],
        "sanitize": ["sanitize"], "xss": ["sanitize"], "injection": ["sanitize"], "clean": ["sanitize"],
        # Business logic keywords
        "invoice": ["invoice_calculator"], "bill": ["invoice_calculator"], "tax": ["invoice_calculator"],
        "discount": ["invoice_calculator"], "calculate": ["invoice_calculator"],
        "inventory": ["inventory_tracker"], "stock": ["inventory_tracker"], "warehouse": ["inventory_tracker"],
        "crm": ["crm_pipeline"], "lead": ["crm_pipeline"], "sales": ["crm_pipeline"], "pipeline": ["crm_pipeline"],
        "task": ["task_scheduler"], "schedule": ["task_scheduler"], "assign": ["task_scheduler"],
        "priority": ["task_scheduler"],
        "report": ["report_generator"], "summary": ["report_generator"], "statistics": ["report_generator"],
        "notification": ["notification_dispatch"], "alert": ["notification_dispatch"],
        "notify": ["notification_dispatch"], "send": ["notification_dispatch", "email_send"],
        "analyze": ["data_analyzer"], "analysis": ["data_analyzer"], "stats": ["data_analyzer"],
        "metrics": ["data_analyzer"],
        # Data keywords
        "create": ["crud_create"], "insert": ["crud_create"], "add": ["crud_create"],
        "read": ["crud_read"], "list": ["crud_read"], "find": ["crud_read"], "query": ["crud_read"],
        "update": ["crud_update"], "modify": ["crud_update"], "edit": ["crud_update"],
        "delete": ["crud_delete"], "remove": ["crud_delete"],
        "transform": ["data_transform"], "map": ["data_transform"], "filter": ["data_transform"],
        "aggregate": ["data_transform"],
        # Integration keywords
        "email": ["email_send"], "smtp": ["email_send"], "mail": ["email_send"],
        "http": ["http_request"], "api": ["http_request"], "request": ["http_request"],
        "rest": ["http_request"],
        "webhook": ["webhook_call"], "callback": ["webhook_call"],
        "file": ["file_operation"], "write": ["file_operation"], "upload": ["file_operation"],
        # Auth keywords
        "login": ["auth_login"], "signin": ["auth_login"], "authenticate": ["auth_login"],
        "register": ["auth_register"], "signup": ["auth_register"],
        "verify": ["auth_verify"], "token": ["auth_verify"], "jwt": ["auth_verify"],
        "permission": ["auth_rbac"], "role": ["auth_rbac"], "access": ["auth_rbac"],
        "rbac": ["auth_rbac"], "authorize": ["auth_rbac"],
        # Category keywords
        "business_logic": ["invoice_calculator", "inventory_tracker", "crm_pipeline",
                           "task_scheduler", "report_generator", "notification_dispatch", "data_analyzer"],
        "integrations": ["email_send", "http_request", "webhook_call", "file_operation"],
        "auth": ["auth_login", "auth_register", "auth_verify", "auth_rbac"],
        "data": ["crud_create", "crud_read", "crud_update", "crud_delete", "data_transform"],
        "flow": ["conditional", "loop", "parallel", "switch", "try_catch"],
        "validation": ["validate_required", "validate_types", "validate_ranges", "validate_unique", "sanitize"],
    }


# ============================================================
#  TEMPLATE BLOCK MAPPING
# ============================================================


def map_template_block(template_name: str) -> Optional[str]:
    """Mapea nombres de bloques del TemplateEngine a bloques del LogicBuilder.

    Args:
        template_name: Block name from the TemplateEngine

    Returns:
        Corresponding LogicBuilder block name, or None if no mapping exists
    """
    mapping = {
        "invoice_calculator": "invoice_calculator",
        "inventory_tracker": "inventory_tracker",
        "crm_pipeline": "crm_pipeline",
        "task_scheduler": "task_scheduler",
        "report_generator": "report_generator",
        "notification_manager": "notification_dispatch",
        "data_analyzer": "data_analyzer",
        "email_smtp": "email_send",
        "webhook_server": "webhook_call",
        "jwt_auth": "auth_login",
        "rbac": "auth_rbac",
        "api_key_auth": "auth_verify",
        "crud_service": "crud_create",
        "migration": "data_transform",
        "backup_restore": "file_operation",
        "seed_data": "crud_create",
    }
    return mapping.get(template_name)


def get_block_template_code(template_engine: Optional[Any], block_name: str) -> Optional[str]:
    """Obtiene codigo de template del TemplateEngine si esta disponible.

    Args:
        template_engine: Instance of TemplateEngine, or None
        block_name: Name of the block to get template code for

    Returns:
        Template code string if available, None otherwise
    """
    if not template_engine:
        return None

    # Map to template engine block name
    template_mapping = {
        "invoice_calculator": "invoice_calculator",
        "inventory_tracker": "inventory_tracker",
        "crm_pipeline": "crm_pipeline",
        "task_scheduler": "task_scheduler",
        "report_generator": "report_generator",
        "notification_dispatch": "notification_manager",
        "data_analyzer": "data_analyzer",
        "email_send": "email_smtp",
        "webhook_call": "webhook_server",
        "auth_login": "jwt_auth",
        "auth_rbac": "rbac",
        "crud_create": "crud_service",
    }

    template_name = template_mapping.get(block_name)
    if not template_name:
        return None

    try:
        block = template_engine.get_block(template_name)
        if block and block.template_path:
            # Return a function call that would use the template
            return f'_execute_block("{block_name}", payload, context)'
    except Exception as template_err:
        logger.debug(f"Template block codegen failed: {template_err}")

    return None


# ============================================================
#  CODE GENERATION
# ============================================================


def generate_inline_block_code(block_name: str, var_name: str) -> List[str]:
    """Genera codigo inline para un bloque especifico.

    Args:
        block_name: Name of the block to generate code for
        var_name: Variable name to use in generated code

    Returns:
        List of code lines for the inline block
    """
    code_generators = {
        "validate_required": [
            f'{var_name} = self._validate_required(payload, payload.get("required_fields", []))',
        ],
        "validate_types": [
            f'{var_name} = self._validate_types(payload, payload.get("type_schema", {{}}))',
        ],
        "validate_ranges": [
            f'{var_name} = self._validate_ranges(payload, payload.get("range_schema", {{}}))',
        ],
        "validate_unique": [
            f'{var_name} = self._validate_unique(payload.get("unique_field", "email"), payload.get("table", "users"), context)',
        ],
        "sanitize": [
            'payload = self._sanitize(payload)',
            f'{var_name} = {{"sanitized": True, "data": payload}}',
        ],
        "invoice_calculator": [
            f'{var_name} = self._calculate_invoice(payload.get("items", []), payload.get("tax_rate", 0.16), payload.get("discount", 0))',
        ],
        "inventory_tracker": [
            f'{var_name} = self._track_inventory(payload.get("product_id"), payload.get("quantity_change", 0), payload.get("operation", "adjust"), context)',
        ],
        "crm_pipeline": [
            f'{var_name} = self._process_crm_lead(payload.get("lead_data", {{}}), payload.get("action", "advance"))',
        ],
        "task_scheduler": [
            f'{var_name} = self._schedule_tasks(payload.get("tasks", []), payload.get("resources", []))',
        ],
        "report_generator": [
            f'{var_name} = self._generate_report(payload.get("data", []), payload.get("report_type", "summary"))',
        ],
        "notification_dispatch": [
            f'{var_name} = self._dispatch_notification(payload.get("recipient", {{}}), payload.get("message", ""), payload.get("channels", ["email"]), context)',
        ],
        "data_analyzer": [
            f'{var_name} = self._analyze_data(payload.get("dataset", []), payload.get("metrics", ["mean", "median", "std"]))',
        ],
        "crud_create": [
            f'{var_name} = self._crud_create(payload, payload.get("table", "items"), context)',
        ],
        "crud_read": [
            f'{var_name} = self._crud_read(payload.get("table", "items"), payload.get("filters", {{}}), payload.get("page", 1), payload.get("page_size", 20), context)',
        ],
        "crud_update": [
            f'{var_name} = self._crud_update(payload.get("table", "items"), payload.get("id"), payload.get("fields", {{}}), context)',
        ],
        "crud_delete": [
            f'{var_name} = self._crud_delete(payload.get("table", "items"), payload.get("id"), context)',
        ],
        "data_transform": [
            f'{var_name} = self._transform_data(payload.get("data", []), payload.get("transform_type", "identity"), payload.get("config", {{}}))',
        ],
        "email_send": [
            f'{var_name} = self._send_email(payload.get("to", ""), payload.get("subject", ""), payload.get("body", ""), context)',
        ],
        "http_request": [
            f'{var_name} = self._http_request(payload.get("url", ""), payload.get("method", "GET"), payload.get("headers", {{}}), payload.get("body"), context)',
        ],
        "webhook_call": [
            f'{var_name} = self._webhook_call(payload.get("url", ""), payload.get("payload", {{}}), payload.get("secret", ""), context)',
        ],
        "file_operation": [
            f'{var_name} = self._file_operation(payload.get("path", ""), payload.get("operation", "read"), payload.get("content", ""), context)',
        ],
        "auth_login": [
            f'{var_name} = self._auth_login(payload.get("username", ""), payload.get("password", ""), context)',
        ],
        "auth_register": [
            f'{var_name} = self._auth_register(payload, context)',
        ],
        "auth_verify": [
            f'{var_name} = self._auth_verify(payload.get("token", ""), context)',
        ],
        "auth_rbac": [
            f'{var_name} = self._check_rbac(payload.get("user_role", "guest"), payload.get("resource", ""), payload.get("action", "read"), context)',
        ],
        "conditional": [
            f'{var_name} = self._conditional_check(payload, payload.get("field", ""), payload.get("value"), payload.get("operator", "=="))',
        ],
        "loop": [
            f'{var_name} = self._loop_items(payload.get("items", []), payload.get("items_field", "items"), context)',
        ],
        "parallel": [
            f'{var_name} = self._parallel_execute(payload.get("_parallel_blocks", []), payload, context)',
        ],
        "switch": [
            f'{var_name} = self._switch_case(payload, payload.get("field", "type"), payload.get("cases", {{}}))',
        ],
        "try_catch": [
            f'{var_name} = self._try_catch(payload, context)',
        ],
    }

    return code_generators.get(block_name, [f'{var_name} = self._execute_block("{block_name}", payload, context)'])


def safe_var_name(block_name: str) -> str:
    """Convierte nombre de bloque a nombre de variable seguro.

    Args:
        block_name: Block name to convert

    Returns:
        Safe variable name string
    """
    return re.sub(r'[^a-z0-9_]', '_', block_name)
