"""
TemplateEngine — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.template_engine import TemplateEngine``
still works exactly as before.
"""

import os
from ._imports import (
    logger, JINJA2_AVAILABLE, _LOAD_FAILED, TEMPLATE_ROOT,
    TemplateBlock, CompositionPlan, Any, Optional,
)
from ._core_mixin import CoreRenderMixin
from ._block_mixin import BlockNicheMixin
from ._resolve_mixin import ResolveMixin
from ._builtin_mixin import BuiltinMixin
from ._utils_mixin import UtilsMixin


class TemplateEngine(CoreRenderMixin, BlockNicheMixin, ResolveMixin,
                     BuiltinMixin, UtilsMixin):
    """
    Motor de templates Jinja2 para generacion de codigo.

    Carga templates desde el filesystem, los compone con bloques
    especializados, y genera codigo funcional completo.
    """

    def __init__(self, template_root: str = ""):
        self._root = template_root or TEMPLATE_ROOT
        self._blocks = {}
        self._env = None
        self._niche_loader = None
        self._dna_loader = None

        if JINJA2_AVAILABLE:
            from jinja2 import Environment, FileSystemLoader
            self._env = Environment(
                loader=FileSystemLoader(self._root),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
                autoescape=False,
            )
            self._env.filters["pascal"] = self._pascal_case
            self._env.filters["snake"] = self._snake_case
            self._env.filters["camel"] = self._camel_case
            self._env.filters["sql_type"] = self._python_to_sql_type
            self._env.filters["sql_param"] = self._to_sql_param
            self._env.filters["default_val"] = self._default_value

        self._register_builtin_blocks()
        logger.info(f"TemplateEngine: Initialized with root={self._root}, jinja2={'yes' if JINJA2_AVAILABLE else 'no'}")


__all__ = [
    "TemplateEngine",
    "TemplateBlock",
    "CompositionPlan",
    "JINJA2_AVAILABLE",
    "TEMPLATE_ROOT",
]
