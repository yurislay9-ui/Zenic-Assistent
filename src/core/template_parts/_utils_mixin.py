"""
Utility and fallback methods mixin for TemplateEngine.
"""

import os
import re

from ._imports import logger, JINJA2_AVAILABLE


class UtilsMixin:
    """Utility methods and fallback rendering for TemplateEngine."""

    @staticmethod
    def _pascal_case(s: str) -> str:
        return "".join(w.capitalize() for w in s.replace("-", "_").split("_"))

    @staticmethod
    def _snake_case(s: str) -> str:
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', s)
        return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    @staticmethod
    def _camel_case(s: str) -> str:
        parts = s.replace("-", "_").split("_")
        return parts[0] + "".join(w.capitalize() for w in parts[1:])

    @staticmethod
    def _python_to_sql_type(py_type: str) -> str:
        mapping = {
            "int": "INTEGER", "float": "REAL", "bool": "INTEGER",
            "str": "TEXT", "datetime": "TEXT", "date": "TEXT",
            "list": "TEXT", "dict": "TEXT", "bytes": "BLOB",
            "Decimal": "REAL",
        }
        return mapping.get(py_type, "TEXT")

    @staticmethod
    def _to_sql_param(value) -> str:
        """Convierte un valor a parametro SQL seguro (?)."""
        return "?"

    @staticmethod
    def _default_value(py_type: str) -> str:
        mapping = {
            "int": "None", "float": "None", "bool": "None",
            "str": '""', "datetime": "None", "date": "None",
            "list": "[]", "dict": "{}",
        }
        return mapping.get(py_type, "None")

    def _fallback_render(self, template_path: str, variables: dict) -> str:
        """Fallback: carga template como texto y hace substitucion simple."""
        full_path = os.path.join(self._root, template_path)
        if not os.path.isfile(full_path):
            return f"# Template not found: {template_path}\n"
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return self._simple_substitute(content, variables)

    @staticmethod
    def _simple_substitute(template_str: str, variables: dict) -> str:
        """Substitucion simple de {{ variable }} sin Jinja2."""
        def replace_var(match):
            var_name = match.group(1).strip()
            parts = var_name.split(".")
            value = variables
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, f"{{{{{var_name}}}}}")
                else:
                    return f"{{{{{var_name}}}}}"
            return str(value) if value is not None else f"{{{{{var_name}}}}}"

        result = re.sub(r'\{\{\s*([^}]+)\s*\}\}', replace_var, template_str)
        result = re.sub(r'\{%\s*end.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*if\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*for\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*block\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*extends\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*include\s+.*?\s*%\}', '', result)
        return result

    @property
    def available_templates(self) -> list:
        """Lista templates disponibles en el filesystem."""
        templates = []
        for root, dirs, files in os.walk(self._root):
            for f in files:
                if f.endswith(".j2"):
                    rel = os.path.relpath(os.path.join(root, f), self._root)
                    templates.append(rel)
        return sorted(templates)

    @property
    def stats(self) -> dict:
        """Estadisticas del motor de templates."""
        stats = {
            "template_root": self._root,
            "jinja2_available": JINJA2_AVAILABLE,
            "registered_blocks": len(self._blocks),
            "block_categories": list(set(b.category for b in self._blocks.values())),
            "available_templates": len(self.available_templates),
        }
        loader = self._get_niche_loader()
        if loader:
            niche_stats = loader.stats
            stats["niche_templates"] = niche_stats.get("total_niches", 0)
            stats["niche_domains"] = niche_stats.get("total_domains", 0)
            stats["niche_entities"] = niche_stats.get("total_entities", 0)
        return stats
