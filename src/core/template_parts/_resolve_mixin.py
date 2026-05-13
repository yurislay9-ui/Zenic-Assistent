"""
Template resolution and variable preparation mixin for TemplateEngine.
"""

import os
from ._imports import logger, _secrets


class ResolveMixin:
    """Template resolution and variable preparation for TemplateEngine."""

    def _resolve_template(self, plan, filename: str):
        """Resuelve la ruta del template mas especifico disponible."""
        if plan.app_template:
            app_path = f"apps/{plan.app_template}/{filename}.j2"
            if self._template_exists(app_path):
                return app_path
        base_path = f"apps/base/{filename}.j2"
        if self._template_exists(base_path):
            return base_path
        logger.debug(f"TemplateEngine: No template found for {filename}")
        return None

    def _resolve_automation_template(self, plan, filename: str):
        """Resuelve la ruta del template de automatizacion."""
        if plan.app_template:
            app_path = f"automations/{plan.app_template}/{filename}.j2"
            if self._template_exists(app_path):
                return app_path
        base_path = f"automations/base/{filename}.j2"
        if self._template_exists(base_path):
            return base_path
        return None

    def _template_exists(self, path: str) -> bool:
        """Verifica si un template existe en el filesystem."""
        full_path = os.path.join(self._root, path)
        return os.path.isfile(full_path)

    def _prepare_variables(self, plan) -> dict:
        """Prepara las variables para renderizar templates."""
        variables = dict(plan.variables)
        processed_entities = []
        for entity in plan.entities:
            processed = self._process_entity(entity)
            processed_entities.append(processed)
        variables["entities"] = processed_entities

        variables["blocks"] = []
        for block_name in plan.blocks:
            block = self._blocks.get(block_name)
            if block:
                variables["blocks"].append({
                    "name": block.name,
                    "category": block.category,
                    "description": block.description,
                    "inputs": block.inputs,
                    "outputs": block.outputs,
                })

        variables.setdefault("project_name", "app")
        variables.setdefault("app_name", variables.get("project_name", "app"))
        variables.setdefault("template_type", "generic")
        variables.setdefault("db_name", variables.get("project_name", "app") + ".db")
        variables.setdefault("port", 8000)
        variables.setdefault("secret_key", _secrets.token_urlsafe(32))
        variables.setdefault("debug", True)
        variables.setdefault("version", "1.0.0")
        return variables

    def _process_entity(self, entity: dict) -> dict:
        """Procesa una entidad para generar variables de template."""
        name = entity.get("name", "Item")
        fields = entity.get("fields", [])
        processed_fields = []
        for f in fields:
            parts = f.split(":")
            fname = parts[0]
            ftype = parts[1] if len(parts) > 1 else "str"
            processed_fields.append({
                "name": fname,
                "type": ftype,
                "sql_type": self._python_to_sql_type(ftype),
                "pascal_name": self._pascal_case(fname),
                "snake_name": self._snake_case(fname),
                "default": self._default_value(ftype),
                "is_fk": fname.endswith("_id") and fname != "id",
                "fk_ref": fname.replace("_id", "") if fname.endswith("_id") and fname != "id" else None,
                "is_indexed": fname in ["name", "status", "type", "category", "date",
                                        "customer_id", "product_id", "user_id", "project_id"],
                "is_unique": fname in ["email", "sku", "code", "slug", "token"],
                "input_type": {"int": "number", "float": "number", "datetime": "datetime-local",
                               "bool": "checkbox"}.get(ftype, "text"),
            })
        return {
            "name": name,
            "name_lower": name.lower(),
            "name_pascal": self._pascal_case(name),
            "name_snake": self._snake_case(name),
            "fields": processed_fields,
            "has_fk": any(f["is_fk"] for f in processed_fields),
        }
