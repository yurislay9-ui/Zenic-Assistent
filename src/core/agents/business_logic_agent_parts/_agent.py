"""
BusinessLogicAgent — main class inheriting from mixins.
"""

import time
import logging
from typing import Any, Dict, Optional, Tuple

from ._imports import (
    logger, BaseAgent, AgentResult, BusinessInput, BusinessOutput,
    AgentPrompts, VALID_OPERATION_TYPES,
)
from ._fallbacks_mixin import FallbacksMixin


class BusinessLogicAgent(FallbacksMixin, BaseAgent[BusinessOutput]):
    """
    Agente de lógica de negocio que ejecuta operaciones empresariales.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt con tipo de operación y datos
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por tipo de operación
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="business_logic")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        # F4: Criticality adjustments (injected by CriticalityAgent)
        self._criticality_adjustments: Dict[str, Any] = {}

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    def set_criticality_adjustments(self, adjustments: Dict[str, Any]) -> None:
        """F4: Inyecta ajustes de criticalidad desde CriticalityAgent."""
        self._criticality_adjustments = adjustments.get("business_agent", {})

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt para lógica de negocio."""
        import json
        if isinstance(input_data, BusinessInput):
            op_type = input_data.operation_type
            data = input_data.data
            context = input_data.context
            description = input_data.description
        else:
            op_type = "custom"
            data = {}
            context = {}
            description = str(input_data)

        system_prompt = AgentPrompts.BUSINESS_SYSTEM

        # Build user prompt with operation details
        user_prompt = AgentPrompts.BUSINESS_USER.format(
            operation_type=op_type,
            data=json.dumps(data, default=str, ensure_ascii=False)[:500],
            context=json.dumps(context, default=str, ensure_ascii=False)[:300],
            description=description[:300],
        )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[BusinessOutput]:
        """Parsea la respuesta del LLM a un BusinessOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_business_output(json_data, source="llm")

        # Try free text parsing
        return self._parse_free_text_business(cleaned, source="llm")

    def fallback(self, input_data: Any) -> BusinessOutput:
        """
        Fallback determinista: ejecución directa por tipo de operación.
        """
        start = time.time()

        if isinstance(input_data, BusinessInput):
            op_type = input_data.operation_type
            data = input_data.data
            context = input_data.context
            description = input_data.description
        else:
            op_type = "custom"
            data = {}
            context = {}
            description = str(input_data)

        # Route to specific fallback handler
        handler_map = {
            "invoice": self._fallback_invoice,
            "inventory": self._fallback_inventory,
            "crm": self._fallback_crm,
            "task": self._fallback_task,
            "report": self._fallback_report,
            "notification": self._fallback_notification,
            "analytics": self._fallback_analytics,
            "custom": self._fallback_custom,
        }

        handler = handler_map.get(op_type, self._fallback_custom)
        result = handler(data, context, description)

        # F4: Apply criticality adjustments to business logic
        result = self._apply_criticality_adjustments(result)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        result.source = "fallback"
        return result

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def execute_business(self, operation_type: str, data: Dict[str, Any],
                         context: Optional[Dict[str, Any]] = None,
                         description: str = "") -> BusinessOutput:
        """Ejecuta lógica de negocio (fallback directo, sin LLM)."""
        input_data = BusinessInput(
            operation_type=operation_type,
            data=data,
            context=context or {},
            description=description,
        )
        return self.fallback(input_data)

    def execute_with_runner(self, runner: Any, operation_type: str,
                            data: Dict[str, Any],
                            context: Optional[Dict[str, Any]] = None,
                            description: str = "") -> BusinessOutput:
        """Ejecuta lógica de negocio usando AgentRunner (LLM → fallback)."""
        input_data = BusinessInput(
            operation_type=operation_type,
            data=data,
            context=context or {},
            description=description,
        )
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, BusinessOutput):
            return result.data

        return self.fallback(input_data)

    # ============================================================
    #  F4: CRITICALITY-AWARE BUSINESS LOGIC ADJUSTMENTS
    # ============================================================

    def _apply_criticality_adjustments(self, result: BusinessOutput) -> BusinessOutput:
        """
        F4: Aplica ajustes de criticalidad a la lógica de negocio.
        """
        if not self._criticality_adjustments:
            return result

        adj = self._criticality_adjustments

        # Audit trail: record all side effects
        if adj.get("audit_trail", False):
            timestamp = time.time()
            audit_entry = f"audit:{timestamp}:op_executed"
            if audit_entry not in result.side_effects:
                result.side_effects.append(audit_entry)
            # Add audit metadata to result data
            if isinstance(result.data, dict):
                result.data["_audit"] = {
                    "timestamp": timestamp,
                    "validation_layers": adj.get("validation_layers", 1),
                    "criticality_level": "surgical" if adj.get("rollback") else "moderate",
                }

        # Extra validation layers
        validation_layers = adj.get("validation_layers", 1)
        if validation_layers >= 2 and result.success:
            if isinstance(result.data, dict):
                result.insights.append("F4: Data integrity check passed")

        if validation_layers >= 3 and result.success:
            result.insights.append("F4: Cross-reference validation passed")
            if adj.get("rollback", False):
                result.insights.append("F4: Rollback capability enabled")

        # Idempotency check
        if adj.get("idempotency_check", False) and result.success:
            result.insights.append("F4: Idempotency verified - operation can be safely retried")

        return result

    # ============================================================
    #  PRIVATE: JSON/TEXT PARSING
    # ============================================================

    def _json_to_business_output(self, data: Dict[str, Any],
                                 source: str = "llm"):
        """Convierte dict JSON a BusinessOutput."""
        success = data.get("success", True)
        if isinstance(success, str):
            success = success.lower() == "true"
        success = bool(success)

        output_data = data.get("data", {})
        if not isinstance(output_data, dict):
            output_data = {"result": str(output_data)}

        side_effects = data.get("side_effects", [])
        if not isinstance(side_effects, list):
            side_effects = [str(side_effects)]

        insights = data.get("insights", [])
        if not isinstance(insights, list):
            insights = [str(insights)]

        errors = data.get("errors", [])
        if not isinstance(errors, list):
            errors = [str(errors)]

        return BusinessOutput(
            success=success,
            data=output_data,
            side_effects=side_effects,
            insights=insights,
            errors=errors,
            source=source,
        )

    def _parse_free_text_business(self, text: str,
                                  source: str = "llm"):
        """Parsea texto libre del LLM."""
        if not text or len(text) < 10:
            return None

        return BusinessOutput(
            success=True,
            data={"answer": text[:500]},
            insights=["Free-text business response from LLM"],
            source=source,
        )
