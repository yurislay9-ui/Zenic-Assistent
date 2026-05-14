"""
ValidationAgent BaseAgent interface + high-level API mixin.
"""

import time
import logging
from typing import Any, Optional, List, Tuple

from ._imports import (
    BaseAgent, AgentResult, AgentPrompts,
    ValidationInput, ValidationOutput, ValidationIssue,
    logger,
)


class BaseInterfaceMixin:
    """BaseAgent interface methods and high-level API for ValidationAgent."""

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt para validación."""
        if isinstance(input_data, ValidationInput):
            target = input_data.target
            content = input_data.content
            rules = input_data.rules
            language = input_data.language
        else:
            target = "code"
            content = str(input_data)
            rules = []
            language = "python"

        system_prompt = AgentPrompts.VALIDATION_SYSTEM
        user_prompt = AgentPrompts.VALIDATION_USER.format(
            target=target,
            content=content[:800],
            rules=", ".join(rules) if rules else "standard",
            language=language,
        )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[Any]:
        """Parsea la respuesta del LLM a un ValidationOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction first
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_validation_output(json_data, source="llm")

        # Try free text parsing
        return self._parse_free_text_validation(cleaned, source="llm")

    def fallback(self, input_data: Any) -> Optional[ValidationOutput]:
        """
        Fallback determinista: validación por reglas estáticas.

        Sin LLM, sin embeddings. Reglas deterministas de seguridad,
        calidad y compatibilidad.
        """
        start = time.time()

        if isinstance(input_data, ValidationInput):
            target = input_data.target
            content = input_data.content
            rules = input_data.rules
            language = input_data.language
        else:
            target = "code"
            content = str(input_data)
            rules = []
            language = "python"

        # Route to target-specific validation
        if target == "chain":
            output = self._validate_chain(content)
        elif target == "config":
            output = self._validate_config(content)
        else:
            output = self._validate_code(content, language, rules)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        output.source = "fallback"
        return output

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def validate_with_runner(self, runner: Any, target: str, content: str,
                              rules: Optional[List[str]] = None,
                              language: str = "python") -> ValidationOutput:
        """Valida usando AgentRunner (LLM → fallback)."""
        input_data = ValidationInput(
            target=target, content=content,
            rules=rules or [], language=language,
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, ValidationOutput):
            return result.data
        return self.fallback(input_data)

    # ============================================================
    #  COMPATIBILITY: ChainValidator contract preserved
    # ============================================================

    def to_validation_result(self, output: ValidationOutput) -> Any:
        """
        Convierte ValidationOutput a ChainValidator.ValidationResult
        para compatibilidad con el pipeline existente.

        NOTE: ChainValidator module has been deleted. This method now
        returns a simple dict-based compatibility shim instead.
        """
        # ChainValidator removed — module deleted
        # Return a dict-based compatibility result instead of ValidationResult
        errors = [
            {"code": i.code, "message": i.message, "block_name": ""}
            for i in output.issues if i.severity == "error"
        ]
        warnings = [
            {"code": i.code, "message": i.message, "block_name": ""}
            for i in output.issues if i.severity != "error"
        ]
        return {
            "is_valid": output.is_valid,
            "can_execute": output.is_valid or not errors,
            "errors": errors,
            "warnings": warnings,
        }
