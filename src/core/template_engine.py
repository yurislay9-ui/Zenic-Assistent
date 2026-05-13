"""
ZENIC-AGENTS - TemplateEngine (Jinja2-Powered Code Generation + Niche Templates)

Motor de templates externos que reemplaza los f-strings inline.
Carga templates .j2 desde src/templates/, los compone con bloques,
y genera codigo funcional, no stubs.
"""

from .template_parts import *  # noqa: F401,F403
from .template_parts import TemplateEngine, TemplateBlock, CompositionPlan  # explicit

__all__ = ["TemplateEngine", "TemplateBlock", "CompositionPlan"]
