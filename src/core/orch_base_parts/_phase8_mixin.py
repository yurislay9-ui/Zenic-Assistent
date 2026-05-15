"""
Phase 8 Intelligence API mixin for BaseOrchestrator.
"""

from ._imports import logger
# AppGenerator removed — module deleted
# RecoveryAction removed — module deleted
# ChainExecutor removed — module deleted


class Phase8Mixin:
    """Phase 8: Intelligence API methods for BaseOrchestrator."""

    async def reason(self, query: str, mode: str = "auto",
                     context: str = "") -> dict:
        """Razonamiento avanzado usando ReasoningAgent (F3) o ReasoningEngine (Legacy)."""
        if self._reasoning_agent:
            actual_mode = mode if mode != "auto" else "step_by_step"
            output = self._reasoning_agent.reason_with_runner(
                self._agent_runner, query, mode=actual_mode, context=context,
            )
            return {
                "answer": output.answer,
                "confidence": output.confidence,
                "mode": output.mode,
                "steps": len(output.steps),
                "refinements": output.refinements,
                "context_used": output.context_used,
                "memory_hits": output.memory_hits,
                "source": output.source,
                "duration_ms": output.total_duration_ms,
            }

        if not self._reasoning:
            return {"error": "ReasoningEngine not available"}

        result = self._reasoning.reason(query, mode=mode, context=context)
        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "mode": result.mode.value,
            "steps": len(result.steps),
            "refinements": result.refinements,
            "context_used": result.context_used,
            "memory_hits": result.memory_hits,
            "source": result.source,
            "duration_ms": result.total_duration_ms,
        }

    async def validate_logic_chain(self, description: str) -> dict:
        """Valida una cadena de logica antes de ejecutarla."""
        if self._validation_agent:
            from src.core.agents.schemas import ValidationInput  # v18 schema type
            output = self._validation_agent.validate_with_runner(
                self._agent_runner, target="chain", content=description,
                rules=["compatibility", "completeness"], language="python",
            )
            result = {
                "is_valid": output.is_valid,
                "can_execute": output.is_valid or not any(
                    i.severity == "error" for i in output.issues
                ),
                "issues": [
                    {"severity": i.severity, "code": i.code,
                     "message": i.message, "line": i.line,
                     "suggestion": i.suggestion}
                    for i in output.issues
                ],
                "suggestions": output.suggestions,
                "risk_score": output.risk_score,
                "source": output.source,
            }
            # ChainValidator removed — legacy chain validation unavailable
            if self._logic_builder:
                chain = self._logic_builder.build_from_description(description)
                result["block_count"] = len(chain.blocks)
            return result

        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}
        # ChainValidator removed — legacy chain validation unavailable
        chain = self._logic_builder.build_from_description(description)
        return {
            "is_valid": None,
            "can_execute": None,
            "errors": [],
            "warnings": [{"code": "DEPRECATED", "message": "ChainValidator removed — legacy validation unavailable", "block": ""}],
            "block_count": len(chain.blocks),
        }

    async def execute_logic_chain(self, description: str,
                                   data=None, recovery: str = "skip") -> dict:
        """Ejecuta una cadena de logica con validacion, rollback y recovery."""
        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}

        # ChainExecutor/RecoveryAction removed — module deleted
        return {"error": "ChainExecutor removed — logic chain execution is no longer available. Use ValidationAgent instead.", "status": "unavailable"}

    async def get_intelligence_status(self) -> dict:
        """Obtiene estado del sistema de inteligencia (Phase 8)."""
        return {
            "reasoning_engine": self._reasoning.stats if self._reasoning else {},
            "ai_layers": {
                "layer1_semantic": {
                    "available": self._semantic.is_loaded if self._semantic else False,
                    "model": "paraphrase-multilingual-MiniLM-L12-v2",
                },
                "layer2_qwen": {
                    "available": self._ai.is_loaded if self._ai else False,
                    "model": "Qwen3-0.6B Q4_K_M",
                },
                "layer3_memory": {
                    "available": self._memory is not None,
                    "stats": self._memory.enhanced_stats if self._memory else {},
                },
            },
            "thinking_engine": self._thinking.stats,
            "phase8_modes": {
                "reasoning": ["step_by_step", "self_reflect", "with_context", "auto"],
                "chain_validation": True,
                "chain_recovery": ["retry", "skip", "fallback", "abort", "rollback"],
            },
        }

    async def get_system_status(self) -> dict:
        """Obtiene estado completo del sistema."""
        return {
            "pipeline": "8-level active",
            "ai": {
                "qwen_loaded": self._ai.is_loaded if self._ai else False,
                "semantic_loaded": self._semantic.is_loaded if self._semantic else False,
                "memory_available": self._memory is not None,
            },
            "thinking_engine": self._thinking.stats,
            "app_templates": {},  # AppGenerator removed — module deleted
            "automation_stats": self._automation.stats,
            "memory_stats": self._memory.enhanced_stats if self._memory else {},
            "phase7_engines": {
                "action_executors": len(self._executor_registry._executors) if self._executor_registry else 0,
                "logic_blocks": len(self._logic_builder.list_blocks()) if self._logic_builder else 0,
                "auth_available": self._auth is not None,
            },
            "phase8_intelligence": {
                "reasoning_available": self._reasoning is not None,
                "chain_validation": True,
                "chain_recovery_modes": 5,
            },
            "agent_framework": {
                "runner_stats": self._agent_runner.stats if self._agent_runner else {},
                "cache_stats": self._agent_runner._cache.stats if self._agent_runner and self._agent_runner._cache else {},
                "intent_agent": getattr(getattr(self, '_surgical_agent', None), 'stats', {}),
                "reasoning_agent": self._reasoning_agent.stats if self._reasoning_agent else {},
                "business_logic_agent": self._business_logic_agent.stats if self._business_logic_agent else {},
                "code_agent": self._code_agent.stats if self._code_agent else {},
                "automation_agent": self._automation_agent.stats if self._automation_agent else {},
                "validation_agent": self._validation_agent.stats if self._validation_agent else {},
            },
            "request_count": self._request_count,
        }
