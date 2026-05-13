"""
Core rendering mixin for TemplateEngine.
"""

import os
from ._imports import logger, JINJA2_AVAILABLE, _secrets


class CoreRenderMixin:
    """Core rendering methods for TemplateEngine."""

    def render(self, template_path: str, variables: dict) -> str:
        """Renderiza un template con las variables dadas."""
        if not JINJA2_AVAILABLE:
            return self._fallback_render(template_path, variables)

        try:
            from jinja2 import TemplateError
            template = self._env.get_template(template_path)
            return template.render(**variables)
        except TemplateError as e:
            logger.error(f"TemplateEngine: Error rendering {template_path}: {e}")
            return self._fallback_render(template_path, variables)

    def render_string(self, template_str: str, variables: dict) -> str:
        """Renderiza un string como template Jinja2."""
        if not JINJA2_AVAILABLE:
            return self._simple_substitute(template_str, variables)

        try:
            from jinja2 import TemplateError
            template = self._env.from_string(template_str)
            return template.render(**variables)
        except TemplateError as e:
            logger.error(f"TemplateEngine: Error rendering string: {e}")
            return self._simple_substitute(template_str, variables)

    def render_app(self, plan) -> dict:
        """Renderiza una aplicacion completa a partir de un CompositionPlan."""
        files = {}
        variables = self._prepare_variables(plan)

        base_files = ["main.py", "database.py", "models.py", "services.py",
                      "config.py", "validators.py", "requirements.txt"]

        for filename in base_files:
            template_path = self._resolve_template(plan, filename)
            if template_path:
                content = self.render(template_path, variables)
                if content:
                    files[filename] = content

        html_files = ["base.html", "dashboard.html", "list.html", "form.html"]
        for filename in html_files:
            template_path = self._resolve_template(plan, f"templates/{filename}")
            if template_path:
                content = self.render(template_path, variables)
                if content:
                    files[f"templates/{filename}"] = content

        css_template = self._resolve_template(plan, "static/style.css")
        if css_template:
            files["static/style.css"] = self.render(css_template, variables)

        for block_name in plan.blocks:
            block = self._blocks.get(block_name)
            if block and block.template_path:
                block_content = self.render(block.template_path, variables)
                if block_content:
                    files[f"blocks/{block_name}.py"] = block_content

        docker_template = self._resolve_template(plan, "Dockerfile")
        if docker_template:
            files["Dockerfile"] = self.render(docker_template, variables)

        readme_template = self._resolve_template(plan, "README.md")
        if readme_template:
            files["README.md"] = self.render(readme_template, variables)

        return files

    def render_automation(self, plan) -> dict:
        """Renderiza un proyecto de automatizacion completo."""
        files = {}
        variables = self._prepare_variables(plan)

        auto_files = ["main.py", "workflows.py", "actions.py", "config.py", "requirements.txt"]

        for filename in auto_files:
            template_path = self._resolve_automation_template(plan, filename)
            if template_path:
                content = self.render(template_path, variables)
                if content:
                    files[filename] = content

        for block_name in plan.blocks:
            block = self._blocks.get(block_name)
            if block and block.template_path:
                block_content = self.render(block.template_path, variables)
                if block_content:
                    files[f"executors/{block_name}.py"] = block_content

        return files
