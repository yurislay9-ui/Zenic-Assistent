"""CodeAssembler - Helpers Mixin."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.code_gen_parts.assembler")


class AssemblerHelpersMixin:
    """Mixin providing helper methods."""

    # ================================================================
    #  HELPERS
    # ================================================================

    @staticmethod
    def _map_type(yaml_type: str) -> str:
        """Map YAML type to Python type annotation."""
        mapping = {
            "str": "str", "string": "str", "text": "str",
            "int": "int", "integer": "int", "number": "int",
            "float": "float", "decimal": "float", "double": "float",
            "bool": "bool", "boolean": "bool",
            "date": "datetime", "datetime": "datetime",
            "list": "List[Any]", "array": "List[Any]",
            "dict": "Dict[str, Any]", "json": "Dict[str, Any]",
            "email": "str", "url": "str", "phone": "str",
        }
        return mapping.get(yaml_type.lower(), "str")

    @staticmethod
    def _block_to_class(block_name: str) -> str:
        """Convert block_name to PascalCase class name."""
        return ''.join(word.capitalize() for word in block_name.split('_'))

    def _prepare_variables(self, project_name: str, entities: List[Dict],
                           blocks: List[str]) -> Dict:
        """Prepare template variables for rendering."""
        entity_names = [e.get("name", "Item") for e in entities]
        entity_fields = {}
        for e in entities:
            name = e.get("name", "Item")
            fields = e.get("fields", [])
            entity_fields[name] = [f.get("name", "field") for f in fields]

        return {
            "project_name": project_name,
            "entities": entities,
            "entity_names": entity_names,
            "entity_fields": entity_fields,
            "blocks": blocks,
            "app_name": project_name,
            "version": "1.0.0",
        }

    def _resolve_dependencies(self, block_names: List[str]) -> List[str]:
        """Resolve block dependencies in correct order."""
        # Define dependency graph
        deps = {
            "rbac": ["jwt_auth"],
            "backup_restore": ["crud_service"],
            "seed_data": ["crud_service"],
        }

        resolved = []
        visited = set()

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            for dep in deps.get(name, []):
                if dep in block_names:
                    visit(dep)
            resolved.append(name)

        for name in block_names:
            visit(name)

        return resolved
