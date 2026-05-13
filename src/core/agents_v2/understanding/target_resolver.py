"""
A03 TargetResolver — SINGLE RESPONSIBILITY: Resolve target file/component and programming language.

Deterministic. Uses EntityResult to determine what the user is targeting.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import EntityResult, TargetResult


class TargetResolver(BaseAgent[TargetResult]):
    """
    A03: Resolve target file and language.

    Single Responsibility: Target resolution ONLY.
    Method: Entity analysis + template composition.
    Fallback: Default to "untitled.py" / python.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A03_TargetResolver", **kwargs)

    def execute(self, input_data: Any) -> TargetResult:
        """
        Resolve target from EntityResult.

        input_data should be a dict with:
          - 'entity_result': EntityResult from A02
          - 'message': original user message (optional)
        """
        entity_result = None
        message = ""

        if isinstance(input_data, dict):
            entity_result = input_data.get("entity_result")
            message = input_data.get("message", "")
        elif isinstance(input_data, EntityResult):
            entity_result = input_data

        if not entity_result or not isinstance(entity_result, EntityResult):
            return self.fallback(input_data)

        # Resolve target file
        target_file = self._resolve_target_file(entity_result, message)
        language = self._resolve_language(entity_result)
        scope = self._resolve_scope(entity_result, message)

        return TargetResult(
            target_file=target_file,
            language=language,
            scope=scope,
            source="deterministic",
        )

    def _resolve_target_file(self, entities: EntityResult, message: str) -> str:
        """Determine the target file from entities."""
        if entities.files:
            return entities.files[0]

        # Compose from domains + operation
        if entities.domains:
            domain = entities.domains[0]
            if entities.frameworks:
                return f"{domain}_{entities.frameworks[0]}.py"
            return f"{domain}_module.py"

        return "untitled.py"

    def _resolve_language(self, entities: EntityResult) -> str:
        """Determine the programming language."""
        if entities.langs:
            return entities.langs[0]
        return "python"

    def _resolve_scope(self, entities: EntityResult, message: str) -> str:
        """Determine the scope of the operation."""
        msg_lower = message.lower() if message else ""
        if any(w in msg_lower for w in ["project", "app", "application", "proyecto", "aplicacion"]):
            return "project"
        elif entities.files:
            return "existing_file"
        else:
            return "new_module"

    def fallback(self, input_data: Any) -> TargetResult:
        return TargetResult(
            target_file="untitled.py",
            language="python",
            scope="new_module",
            source="fallback",
        )
