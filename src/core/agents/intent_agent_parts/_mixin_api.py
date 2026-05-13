"""
Mixin: High-level API and conversion methods for IntentAgent.
"""

from typing import Any

from ._imports import IntentInput, IntentOutput, AgentResult, VALID_OPERATIONS, VALID_GOALS


class ApiMixin:
    """High-level API: classify, classify_with_runner, to_intent_payload."""

    def to_intent_payload(self, output: IntentOutput, context: str = "") -> Any:
        """
        Convierte IntentOutput a IntentPayload para compatibilidad
        con el pipeline existente.

        Este método es el CABLE que conecta el nuevo sistema de agentes
        con el pipeline Legacy.
        """
        from src.core.shared.contracts import IntentPayload, OperationType, GoalType

        # Map string → OperationType/GoalType constants
        op = output.operation if output.operation in VALID_OPERATIONS else OperationType.SEARCH
        goal = output.goal if output.goal in VALID_GOALS else GoalType.FEATURE_ADD

        # Build scrap_query for GitHub search
        scrap_query = ""
        if op in [OperationType.CREATE, OperationType.OPTIMIZE, OperationType.REFACTOR]:
            scrap_query = f"modern {goal} {op} {output.language}"

        return IntentPayload(
            op=op,
            target=output.target or "unknown",
            goal=goal,
            scrap_query=scrap_query,
            confidence=output.confidence,
            language=output.language or "python",
            raw_code="",  # Se rellena aparte si hay código
            context=context,
        )

    def classify(self, message: str, context: str = "") -> IntentOutput:
        """
        Clasifica la intención del usuario.

        Este es el método que el Orchestrator debe llamar.
        Internamente usa AgentRunner.run() → LLM → fallback.

        Args:
            message: Mensaje del usuario
            context: Contexto adicional (conversación previa, etc.)

        Returns:
            IntentOutput con la clasificación completa
        """
        input_data = IntentInput(message=message, context=context)
        return self.fallback(input_data)

    def classify_with_runner(self, runner: Any, message: str,
                             context: str = "") -> IntentOutput:
        """
        Clasifica usando el AgentRunner completo (LLM + fallback).

        Args:
            runner: Instancia de AgentRunner
            message: Mensaje del usuario
            context: Contexto adicional

        Returns:
            IntentOutput
        """
        input_data = IntentInput(message=message, context=context)
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, IntentOutput):
            return result.data

        # Si todo falló, usar fallback directo
        return self.fallback(input_data)
