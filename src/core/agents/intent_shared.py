"""
ZENIC-AGENTS - Intent Shared Constants & Utilities

Shared constants and utility functions used by both IntentAgent and
SurgicalAgent to eliminate code duplication.

Single source of truth for:
- VALID_OPERATIONS, VALID_GOALS, VALID_LANGUAGES
- Keyword maps for TF-IDF classification
- Code block extraction
- Target and language extraction
- Template type inference
- Criticality inference
"""

import re
import logging
from typing import Any, Optional

# ── Import canonical constants (single source of truth) ──
from ..shared.constants import (
    VALID_INTENT_OPERATIONS,
    VALID_INTENT_GOALS,
    VALID_INVENTORY_OPERATIONS,  # noqa: F401 — re-export for backward compat
    VALID_LANGUAGES,
    EXT_LANG_MAP,
    FENCE_LANG_MAP,
)

# Backward-compatible aliases (consumers may import these names)
VALID_OPERATIONS = VALID_INTENT_OPERATIONS
VALID_GOALS = VALID_INTENT_GOALS

logger = logging.getLogger(__name__)


# ============================================================
#  KEYWORD MAPS FOR TF-IDF CLASSIFICATION
# ============================================================

OP_KEYWORDS: dict[str, list[str]] = {
    "CREATE": [
        "crear", "create", "generar", "generate", "hacer", "make",
        "construir", "build", "nuevo", "new", "agregar", "add",
        "implementar", "implement", "desarrollar", "develop",
        "escribir", "write", "definir", "define", "scaffold",
    ],
    "REFACTOR": [
        "refactor", "refactorizar", "reestructurar", "restructure",
        "reorganizar", "reorganize", "mejorar", "improve",
        "limpiar", "clean", "simplificar", "simplify",
        "rediseñar", "redesign", "migrar", "migrate",
    ],
    "DELETE": [
        "eliminar", "delete", "remove", "remover", "borrar",
        "quitar", "drop", "descartar", "discard", "limpiar",
    ],
    "SEARCH": [
        "buscar", "search", "find", "encontrar", "buscar",
        "localizar", "locate", "filtrar", "filter", "query",
    ],
    "ANALYZE": [
        "analizar", "analyze", "examinar", "examine", "revisar",
        "review", "inspeccionar", "inspect", "auditar", "audit",
        "evaluar", "evaluate", "diagnosticar", "diagnose",
    ],
    "EXPLAIN": [
        "explicar", "explain", "describir", "describe",
        "documentar", "document", "comentar", "comment",
        "detallar", "detail", "clarificar", "clarify",
    ],
    "DEBUG": [
        "debug", "depurar", "fix", "arreglar", "corregir",
        "corregir", "reparar", "repair", "resolver", "resolve",
        "error", "bug", "fallo", "failure", "traceback",
    ],
    "OPTIMIZE": [
        "optimizar", "optimize", "mejorar rendimiento", "speed up",
        "acelerar", "accelerate", "reducir", "reduce",
        "eficiente", "efficient", "performance", "rendimiento",
        "rapido", "fast", "cache", "cachear",
    ],
}

GOAL_KEYWORDS: dict[str, list[str]] = {
    "COMPLEXITY_REDUCTION": [
        "simplificar", "simplify", "reducir complejidad",
        "less complex", "mas simple", "clean code",
    ],
    "MODERN_PATTERN": [
        "moderno", "modern", "patron", "pattern", "best practice",
        "mejor practica", "actualizar", "update",
    ],
    "BUG_FIX": [
        "bug", "error", "fallo", "fix", "corregir", "reparar",
        "arreglar", "parche", "patch", "hotfix",
    ],
    "FEATURE_ADD": [
        "nueva funcionalidad", "new feature", "agregar", "add",
        "implementar", "implement", "extender", "extend",
    ],
    "SECURITY_HARDEN": [
        "seguridad", "security", "auth", "jwt", "token",
        "cifrado", "encrypt", "hash", "sanitize", "validar",
    ],
    "PERFORMANCE": [
        "rendimiento", "performance", "velocidad", "speed",
        "optimizar", "optimize", "cache", "async", "paralelo",
    ],
    "READABILITY": [
        "legibilidad", "readability", "documentar", "document",
        "comentar", "comment", "claro", "clear", "nombrar",
    ],
}


# ============================================================
#  SHARED UTILITY FUNCTIONS
# ============================================================

def extract_target_and_language(message: str) -> tuple[str, str]:
    """
    Extrae el nombre del target (archivo/modulo) y el lenguaje del mensaje.

    Returns:
        (target, language) tuple
    """
    target = ""
    language = "python"

    # Pattern: "crear modulo auth.py" / "create file auth.py"
    m = re.search(
        r'(?:modulo|module|archivo|file|clase|class|funcion|function)\s+'
        r'([a-zA-Z_][\w./]*(?:\.\w+)?)',
        message, re.IGNORECASE
    )
    if m:
        target = m.group(1)

    # Pattern: "auth.py" / "user_service.kt" (direct file references)
    if not target:
        m = re.search(r'\b([a-zA-Z_]\w*\.\w+)\b', message)
        if m:
            target = m.group(1)

    # Infer language from extension
    if target and '.' in target:
        ext = '.' + target.rsplit('.', 1)[-1]
        language = EXT_LANG_MAP.get(ext, "python")

    # Pattern: "en Kotlin" / "in Go" / "python"
    lang_match = re.search(
        r'(?:en|in|lenguaje|language)\s+(' + '|'.join(VALID_LANGUAGES) + r')',
        message, re.IGNORECASE
    )
    if lang_match:
        language = lang_match.group(1).lower()

    return target, language


def extract_code_block(message: str) -> tuple[str, str]:
    """
    Extrae código de un bloque de valla (```lang ... ```).

    Returns:
        (language, code) tuple
    """
    # Match fenced code blocks
    m = re.search(r'```(\w+)?\s*\n(.*?)```', message, re.DOTALL)
    if m:
        fence_lang = m.group(1) or ""
        code = m.group(2).strip()
        language = FENCE_LANG_MAP.get(fence_lang.lower(), fence_lang.lower() or "python")
        return language, code

    # Match inline code
    m = re.search(r'`([^`]+)`', message)
    if m:
        code = m.group(1).strip()
        if len(code) > 20 and any(kw in code for kw in ['def ', 'class ', 'import ', 'function ', 'func ']):
            return "python", code

    return "", ""


def extract_entities(message: str) -> dict[str, Any]:
    """Extrae entidades nombradas del mensaje (nombres de archivos, clases, etc.)."""
    entities: dict[str, Any] = {}

    # File references: "auth.py", "user_service.kt"
    files = re.findall(r'\b([a-zA-Z_]\w*\.\w+)\b', message)
    if files:
        entities["files"] = files

    # Class/function names: "class UserService", "def process_order"
    class_names = re.findall(r'\b(?:class|clase)\s+(\w+)', message)
    if class_names:
        entities["classes"] = class_names

    func_names = re.findall(r'\b(?:def|function|func)\s+(\w+)', message)
    if func_names:
        entities["functions"] = func_names

    # Numbers: "16%", "0.5", "100"
    numbers = re.findall(r'\b\d+(?:\.\d+)?%?\b', message)
    if numbers:
        entities["numbers"] = numbers

    return entities


def infer_criticality(operation: str, goal: str, target: str = "") -> str:
    """
    Infiere la criticalidad basándose en operation, goal y target.

    Returns:
        "standard", "moderate", or "critical"
    """
    # Critical patterns
    critical_ops = {"DELETE", "REFACTOR"}
    critical_goals = {"SECURITY_HARDEN", "BUG_FIX"}
    critical_targets = {
        "auth", "login", "password", "token", "jwt",
        "payment", "stripe", "billing", "checkout",
        "permission", "rbac", "admin",
    }

    # Check for critical conditions
    if operation in critical_ops and goal in critical_goals:
        return "critical"

    target_lower = target.lower()
    if any(ct in target_lower for ct in critical_targets):
        if goal == "SECURITY_HARDEN" or operation == "DELETE":
            return "critical"
        return "moderate"

    if operation in critical_ops or goal in critical_goals:
        return "moderate"

    return "standard"


def infer_template_type(operation: str, description: str = "") -> str:
    """
    Infiere el tipo de template basándose en la operación y descripción.

    Returns:
        Template type string (e.g., "auth_system", "crud_dashboard", etc.)
    """
    desc_lower = (description or "").lower()

    template_patterns = {
        "auth_system": ["auth", "login", "jwt", "password", "session"],
        "crud_dashboard": ["crud", "dashboard", "panel", "gestion", "management"],
        "inventory": ["inventario", "inventory", "stock", "almacen", "warehouse"],
        "invoice_billing": ["factura", "invoice", "billing", "pago", "payment"],
        "task_manager": ["tarea", "task", "todo", "proyecto", "project"],
        "crm": ["crm", "cliente", "customer", "venta", "sales"],
        "web_api": ["api", "rest", "endpoint", "servidor", "server"],
        "notification": ["notificacion", "notification", "alerta", "alert", "email"],
    }

    for template_type, keywords in template_patterns.items():
        if any(kw in desc_lower for kw in keywords):
            return template_type

    return "generic"
