"""PipelineOrchestrator - Additional methods."""

import logging
from typing import Any

from ..schemas import IntentResult

logger = logging.getLogger("zenic_agents.agents.pipeline_orchestrator")


class PipelineOrchestratorExtraMixin:
    """Additional methods mixin."""

    def _execute_automation_operation(
        self,
        message: str,
        intent_result: Any,
    ) -> tuple:
        """Execute an automation workflow: infer trigger → action → schedule → conditions → name → serialize."""
        # Step 1: Infer trigger type
        trigger_result = self._run_agent(self._trigger_inferrer, message)
        
        # Step 2: Infer action type
        action_result = self._run_agent(self._action_inferrer, {
            "description": message,
            "trigger_type": trigger_result.type if trigger_result else "manual",
        })
        
        # Step 3: Parse schedule (if applicable)
        schedule_result = self._run_agent(self._schedule_parser, {
            "description": message,
            "trigger_type": trigger_result.type if trigger_result else "manual",
        })
        
        # Step 4: Extract conditions
        condition_result = self._run_agent(self._condition_extractor, {
            "description": message,
        })
        
        # Step 5: Generate name
        name_result = self._run_agent(self._automation_namer, {
            "description": message,
            "trigger_type": trigger_result.type if trigger_result else "manual",
            "action_type": action_result.type if action_result else "log",
        })
        
        # Step 6: Serialize workflow
        workflow_result = self._run_agent(self._workflow_serializer, {
            "name": name_result.name if name_result else "unnamed_workflow",
            "slug": name_result.slug if name_result else "unnamed_workflow",
            "trigger": trigger_result,
            "action": action_result,
            "schedule": schedule_result,
            "conditions": condition_result.conditions if condition_result else [],
        })
        
        return workflow_result, "automation"

    # ══════════════════════════════════════════════════════════
    #  REASONING OPERATION EXECUTION
    # ══════════════════════════════════════════════════════════

    def _execute_reasoning_operation(
        self,
        message: str,
        intent_result: Any,
    ) -> tuple:
        """Execute a reasoning pipeline: detect problem → decompose → reason → confidence → conclusion."""
        # Step 1: Detect problem type
        problem_result = self._run_agent(self._problem_detector, message)
        
        # Step 2: Decompose into steps
        steps_result = self._run_agent(self._step_decomposer, {
            "query": message,
            "problem_type": problem_result.type if problem_result else "general",
            "complexity": problem_result.complexity if problem_result else 0.5,
        })
        
        # Step 3: Apply template reasoning
        reasoning_result = self._run_agent(self._template_reasoner, {
            "query": message,
            "problem_type": problem_result.type if problem_result else "general",
            "steps": steps_result.steps if steps_result else [],
        })
        
        # Step 4: Estimate confidence
        confidence_result = self._run_agent(self._confidence_estimator, {
            "reasoning_result": reasoning_result,
            "problem_type": problem_result.type if problem_result else "general",
        })
        
        # Step 5: Extract conclusion
        conclusion_result = self._run_agent(self._conclusion_extractor, {
            "reasoning_result": reasoning_result,
            "confidence_score": confidence_result.score if confidence_result else 0.0,
        })
        
        return conclusion_result, "reasoning"

    # ══════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _is_automation_intent(message: str, intent_result: Any) -> bool:
        """Detect if the user wants an automation/workflow."""
        automation_keywords = [
            "automate", "automation", "workflow", "trigger", "schedule",
            "cron", "webhook", "automatizar", "automatización", "flujo",
            "programar", "tarea programada", "notificación automática",
        ]
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in automation_keywords):
            return True
        # Also check if the intent goal is related to automation
        if intent_result and isinstance(intent_result, IntentResult):
            if intent_result.operation == "CREATE" and "automat" in message.lower():
                return True
        return False

    @staticmethod
    def _is_reasoning_intent(message: str, intent_result: Any) -> bool:
        """Detect if the user needs reasoning/problem-solving."""
        reasoning_keywords = [
            "why does", "explain why", "how to solve", "what causes",
            "root cause", "investigate", "troubleshoot", "reasoning",
            "por qué", "como resolver", "causa raíz", "investigar",
            "analyze problem", "problem solve", "decompose",
        ]
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in reasoning_keywords):
            return True
        # Check if operation is ANALYZE with high complexity
        if intent_result and isinstance(intent_result, IntentResult):
            if intent_result.operation == "ANALYZE" and intent_result.confidence > 0.5:
                return False  # ANALYZE goes to business by default
        return False

    @staticmethod
    def _infer_business_type(message: str) -> str:
        """Infer business operation type from message keywords."""
        msg_lower = message.lower()
        type_keywords = {
            "invoice": ["invoice", "factura", "billing", "cobro", "pago", "receipt"],
            "inventory": ["inventory", "inventario", "stock", "almacen", "product", "producto"],
            "crm": ["crm", "cliente", "customer", "ventas", "sales", "lead", "pipeline"],
            "task": ["task", "tarea", "scheduling", "calendar", "agenda", "appointment"],
            "report": ["report", "reporte", "informe", "dashboard", "resumen", "summary"],
            "notification": ["notification", "notificacion", "alert", "alerta", "notify", "aviso"],
            "analytics": ["analytics", "analisis", "analysis", "statistics", "stats", "metric"],
        }
        for biz_type, keywords in type_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                return biz_type
        return "custom"

    def _run_agent(self, agent, input_data: Any) -> Any:
        """Run an agent and extract the data from the result envelope."""
        result = agent.run(input_data)
        if isinstance(result, dict):
            return result.get("data")
        return result

    def get_system_status(self) -> dict[str, Any]:
        """Get full system status."""
        return {
            "circuit_breakers": self._cb_manager.all_stats(),
            "bulkheads": self._bulkhead_manager.all_stats(),
            "health": self._health_monitor.system_health(),
            "audit": self._audit_logger.stats,
            "verdict_engine": self._verdict_engine.verdict_stats,
            "mini_ai_loaded": (
                self._mini_ai is not None
                and getattr(self._mini_ai, 'is_loaded', False)
            ),
            "agents_wired": {
                "understanding": 5,   # A48, A01-A04
                "memory": 4,          # A05-A08
                "business": 8,        # A09-A16
                "code_ops": 0,        # A17-A22 REMOVED (code_ops deleted)
                "validation": 4,      # A23-A28
                "automation": 6,      # A29-A34
                "reasoning": 5,       # A35-A39
                "verdict": 3,         # A40-A43
                "infrastructure": 4,  # A44-A47 (wired externally)
                "total": 39,          # 39 directly wired + 3 infrastructure = 42
            },
        }

