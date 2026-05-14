"""CodeAssembler - Connects templates + YAML + executors to generate code."""

import os
import logging
from typing import Any, Dict, List, Optional

from ._constants import BLOCK_TEMPLATE_MAP, KEYWORD_BLOCK_MAP
from ._generators_mixin import AssemblerGeneratorsMixin
from ._scaffolding_mixin import AssemblerScaffoldingMixin
from ._helpers_mixin import AssemblerHelpersMixin

logger = logging.getLogger("zenic_agents.code_gen_parts.assembler")

__all__ = ["CodeAssembler"]


class CodeAssembler(AssemblerGeneratorsMixin, AssemblerScaffoldingMixin, AssemblerHelpersMixin):
    """Assembles real functional code from Jinja2 templates and niche data."""

    def __init__(self, template_engine=None):
        self._template_engine = template_engine

    # ================================================================
    #  PUBLIC API
    # ================================================================

    def resolve_blocks(self, description: str, niche_plan=None) -> List[str]:
        """Resolve which blocks are needed based on description + niche.

        Args:
            description: User's description of what they want
            niche_plan: Optional CompositionPlan from NicheLoader

        Returns:
            Ordered list of block names (dependencies resolved)
        """
        blocks = set()

        # 1. From niche plan if available
        if niche_plan and hasattr(niche_plan, 'blocks'):
            for b in niche_plan.blocks:
                if b in BLOCK_TEMPLATE_MAP:
                    blocks.add(b)

        # 2. From keyword matching
        desc_lower = description.lower()
        for keyword, block_list in KEYWORD_BLOCK_MAP.items():
            if keyword in desc_lower:
                for b in block_list:
                    blocks.add(b)

        # 3. Always add crud_service if entities exist (every app needs CRUD)
        if niche_plan and hasattr(niche_plan, 'entities') and niche_plan.entities:
            if len(niche_plan.entities) > 0:
                blocks.add("crud_service")

        # 4. Resolve dependency order
        return self._resolve_dependencies(list(blocks))

    def assemble_project(self, description: str, niche_plan=None,
                         project_name: str = "zenic_app",
                         entities: Optional[List[Dict]] = None) -> Dict[str, str]:
        """Assemble a complete project with REAL functional code.

        Args:
            description: What the user wants to build
            niche_plan: Optional CompositionPlan from NicheLoader
            project_name: Name for the generated project
            entities: List of entity dicts from niche YAML

        Returns:
            Dict mapping filename -> file content (all real code)
        """
        blocks = self.resolve_blocks(description, niche_plan)
        entities = entities or []
        if niche_plan and hasattr(niche_plan, 'entities') and niche_plan.entities:
            entities = niche_plan.entities

        # Prepare template variables
        variables = self._prepare_variables(project_name, entities, blocks)

        # Render each block
        files = {}
        for block_name in blocks:
            content = self._render_block(block_name, variables)
            if content:
                files[f"blocks/{block_name}.py"] = content

        # Generate entity models
        if entities:
            models_code = self._generate_pydantic_models(entities, project_name)
            files["models.py"] = models_code

        # Generate main.py with proper imports
        main_code = self._generate_main(project_name, blocks, entities)
        files["main.py"] = main_code

        # Generate requirements.txt
        files["requirements.txt"] = self._generate_requirements(blocks)

        # Generate config
        files["config.py"] = self._generate_config(project_name, entities)

        return files

    def build_service_method(self, entity: Dict, operation: str = "crud") -> str:
        """Build a REAL _process() method for a given entity and operation.

        This replaces the stub: return {"processed": True, "input": payload}
        With actual CRUD/transform/validation logic.

        Args:
            entity: Entity dict with 'name', 'fields', etc.
            operation: Type of operation ("crud", "analytics", "notification", etc.)

        Returns:
            Python code string for the _process method
        """
        entity_name = entity.get("name", "item")
        table_name = entity_name.lower() + "s"
        fields = entity.get("fields", [])

        if operation == "crud":
            return self._build_crud_process(entity_name, table_name, fields)
        elif operation == "analytics":
            return self._build_analytics_process(entity_name, table_name, fields)
        elif operation == "notification":
            return self._build_notification_process(entity_name, fields)
        else:
            return self._build_crud_process(entity_name, table_name, fields)

    # ================================================================
    #  BLOCK RENDERING
    # ================================================================

    def _render_block(self, block_name: str, variables: Dict) -> Optional[str]:
        """Render a single block template with variables."""
        template_path = BLOCK_TEMPLATE_MAP.get(block_name)
        if not template_path:
            logger.warning(f"CodeAssembler: No template for block '{block_name}'")
            return None

        # Try Jinja2 rendering via TemplateEngine
        if self._template_engine:
            try:
                content = self._template_engine.render(template_path, variables)
                if content and len(content) > 50:  # Real content, not empty
                    return content
            except Exception as e:
                logger.warning(f"CodeAssembler: Template render failed for {block_name}: {e}")

        # Fallback: read template file and do simple substitution
        return self._fallback_render(template_path, variables)

    def _fallback_render(self, template_path: str, variables: Dict) -> Optional[str]:
        """Fallback rendering without Jinja2."""
        # Find template file
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        full_path = os.path.join(template_dir, template_path)
        if not os.path.exists(full_path):
            # Try absolute path from project root
            full_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", template_path)

        if not os.path.exists(full_path):
            logger.warning(f"CodeAssembler: Template not found: {template_path}")
            return None

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Simple {{ variable }} substitution
            for key, value in variables.items():
                content = content.replace("{{ " + key + " }}", str(value))
                content = content.replace("{{" + key + "}}", str(value))

            return content
        except Exception as e:
            logger.error(f"CodeAssembler: Fallback render failed: {e}")
            return None
