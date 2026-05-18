"""
v1-compatible adapter classes: Surgical, Reasoning, and BusinessLogic.
"""

from __future__ import annotations

from typing import Any, Optional

# v2 agents
from ..understanding import (
    IntentClassifier,
    EntityExtractor,
    TargetResolver,
    CriticalityScorer,
)
from ..reasoning import TemplateReasoner
from ..business import OperationRouter

# v2 schemas
from ..schemas import IntentResult, ReasoningResult

# v1 schema types
from ..schemas._v1_compat_schemas import (
    IntentOutput,
    ReasoningOutput,
    ReasoningStep as V1ReasoningStep,
)

# Shared utilities
from src.core.shared.agent_schemas import (
    ValidationIssue as SharedValidationIssue,
)
from src.core.shared.contracts import IntentPayload, OperationType, GoalType
from ..understanding.intent_utils import (
    extract_code_block,
    extract_target_and_language,
    extract_entities,
    infer_criticality,
    infer_template_type,
)

# Local compat types
from ._types import VALID_OPERATIONS, VALID_GOALS, logger


# ══════════════════════════════════════════════════════════════
#  SurgicalAgentCompat
# ══════════════════════════════════════════════════════════════

class SurgicalAgentCompat:
    """
    v1-compatible SurgicalAgent wrapper around v2 IntentClassifier + friends.

    Preserves the multi-cable fusion behavior:
      - Cable 1: SmartMemory cache
      - Cable 2: SemanticEngine embeddings
      - Cable 3: LLM classification (via v2 agent runner)
      - Cable 4: Keyword scoring (IntentClassifier)

    Provides the v1 API the orchestrator expects:
      - classify_with_runner(runner, msg, ctx) -> IntentOutput
      - to_intent_payload(output, context) -> IntentPayload
      - _extract_code_block(msg) -> (lang, code)  [static]
    """

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._intent_classifier = IntentClassifier(**kwargs)
        self._entity_extractor = EntityExtractor(**kwargs)
        self._target_resolver = TargetResolver(**kwargs)
        self._criticality_scorer = CriticalityScorer(**kwargs)
        self._call_count = 0
        self._last_source = "deterministic"

    # ── v1 API: classify_with_runner ──────────────────────────

    def classify_with_runner(self, runner: Any, message: str,
                             context: str = "") -> IntentOutput:
        """
        Classify intent using v2 agents with multi-cable fusion.

        Replaces: agents.SurgicalAgent.classify_with_runner()
        """
        self._call_count += 1

        # Cable 1: SmartMemory cache
        if self._memory is not None:
            cached = self._memory.check_cache(message)
            if cached:
                self._last_source = "cache"
                return self._cached_to_intent_output(cached, message, context)

        # Cable 2: SemanticEngine embeddings (if available)
        sem_result = None
        if self._semantic and self._semantic.is_loaded:
            sem_result = self._cable_semantic(message)

        # Cable 3: v2 IntentClassifier (keyword scoring)
        classify_result = self._intent_classifier.run(message)
        kw_result = self._v2_result_to_intent_output(
            classify_result, message, context
        )

        # Fusion: combine keyword + semantic results
        if sem_result is not None:
            fused = self._fuse_signals(kw_result, sem_result)
        else:
            fused = kw_result

        # Cache result in SmartMemory
        if self._memory is not None:
            try:
                importance = 0.5 if fused.confidence > 0.5 else 0.3
                self._memory.add_working(
                    message,
                    f"{fused.operation}/{fused.goal}",
                    fused.operation,
                    fused.goal,
                    importance,
                )
                self._memory.save_to_cache(
                    message,
                    f"{fused.operation}/{fused.goal}",
                    fused.operation,
                    fused.goal,
                    importance,
                )
            except Exception:
                pass

        self._last_source = fused.source
        return fused

    def classify(self, message: str, context: str = "") -> IntentOutput:
        """Classify without runner (deterministic only)."""
        return self.classify_with_runner(None, message, context)

    # ── v1 API: to_intent_payload ─────────────────────────────

    def to_intent_payload(self, output: IntentOutput, context: str = "") -> Any:
        """Convert IntentOutput -> IntentPayload for the pipeline."""
        op = output.operation if output.operation in VALID_OPERATIONS else OperationType.SEARCH
        goal = output.goal if output.goal in VALID_GOALS else GoalType.FEATURE_ADD

        scrap_query = ""
        if op in (OperationType.CREATE, OperationType.OPTIMIZE, OperationType.REFACTOR):
            scrap_query = f"modern {goal} {op} {output.language}"

        return IntentPayload(
            op=op,
            target=output.target or "unknown",
            goal=goal,
            scrap_query=scrap_query,
            confidence=output.confidence,
            language=output.language or "python",
            raw_code="",
            context=context,
        )

    # ── v1 API: _extract_code_block (static) ──────────────────

    @staticmethod
    def _extract_code_block(message: str) -> tuple[str, str]:
        """Extract code block from message."""
        return extract_code_block(message)

    # ── Internal helpers ──────────────────────────────────────

    def _cable_semantic(self, message: str) -> Optional[IntentOutput]:
        """Cable 2: SemanticEngine embedding-based classification."""
        if not self._semantic or not self._semantic.is_loaded:
            return None
        try:
            result = self._semantic.classify_intent(message)
            if result and result.get("confidence", 0) > 0.5:
                return IntentOutput(
                    operation=result.get("operation", "SEARCH"),
                    goal=result.get("goal", "FEATURE_ADD"),
                    target="",
                    language="python",
                    confidence=result.get("confidence", 0.5),
                    source="semantic",
                )
        except Exception:
            pass
        return None

    def _v2_result_to_intent_output(
        self, run_result: dict, message: str, context: str
    ) -> IntentOutput:
        """Convert v2 IntentClassifier run() dict result to v1 IntentOutput."""
        target, language = extract_target_and_language(message)
        entities = extract_entities(message)
        criticality = infer_criticality(
            run_result.get("data", {}).operation if isinstance(run_result.get("data"), IntentResult) else "SEARCH",
            run_result.get("data", {}).goal if isinstance(run_result.get("data"), IntentResult) else "FEATURE_ADD",
            target,
        )

        data = run_result.get("data")
        if isinstance(data, IntentResult):
            operation = data.operation
            goal = data.goal
            confidence = data.confidence
            source = data.source
        else:
            operation = "SEARCH"
            goal = "FEATURE_ADD"
            confidence = 0.1
            source = "fallback"

        return IntentOutput(
            operation=operation,
            goal=goal,
            target=target,
            language=language,
            entities=entities,
            template_type=infer_template_type(operation, message),
            criticality=criticality,
            confidence=confidence,
            source=source,
        )

    def _cached_to_intent_output(
        self, cached: dict, message: str, context: str
    ) -> IntentOutput:
        """Convert cached SmartMemory result to IntentOutput."""
        response = cached.get("response", "")
        # Try to parse operation/goal from cached response
        parts = response.split("/", 1)
        operation = parts[0] if parts[0] in VALID_OPERATIONS else "SEARCH"
        goal = parts[1] if len(parts) > 1 and parts[1] in VALID_GOALS else "FEATURE_ADD"
        target, language = extract_target_and_language(message)

        return IntentOutput(
            operation=operation,
            goal=goal,
            target=target,
            language=language,
            confidence=0.6,
            source="cache",
        )

    def _fuse_signals(
        self, primary: IntentOutput, secondary: IntentOutput
    ) -> IntentOutput:
        """Fuse two classification signals (multi-cable fusion)."""
        # If both agree → high confidence
        if primary.operation == secondary.operation and primary.goal == secondary.goal:
            confidence = min(max(primary.confidence, secondary.confidence) + 0.15, 1.0)
            source = "fusion_high"
        # If operations agree, goals differ → medium confidence
        elif primary.operation == secondary.operation:
            confidence = max(primary.confidence, secondary.confidence)
            source = "fusion_partial"
        # Disagreement → keep primary with reduced confidence
        else:
            confidence = max(primary.confidence * 0.7, 0.2)
            source = "fusion_disagree"

        return IntentOutput(
            operation=primary.operation,
            goal=primary.goal,
            target=primary.target,
            language=primary.language,
            entities=primary.entities,
            template_type=primary.template_type,
            criticality=primary.criticality,
            confidence=round(confidence, 2),
            source=source,
        )

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "SurgicalAgentCompat",
            "call_count": self._call_count,
            "last_source": self._last_source,
            "intent_classifier": self._intent_classifier.stats,
        }


# ══════════════════════════════════════════════════════════════
#  ReasoningAgentCompat
# ══════════════════════════════════════════════════════════════

class ReasoningAgentCompat:
    """
    v1-compatible ReasoningAgent wrapper around v2 TemplateReasoner.

    Provides:
      - reason_with_runner(runner, query, mode, context) -> ReasoningOutput
    """

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._reasoner = TemplateReasoner(**kwargs)
        self._call_count = 0

    def reason_with_runner(self, runner: Any, query: str,
                           mode: str = "step_by_step",
                           context: str = "") -> ReasoningOutput:
        """Reason using v2 TemplateReasoner."""
        self._call_count += 1

        input_data = {
            "query": query,
            "context": context,
            "mode": mode,
        }
        result = self._reasoner.run(input_data)

        data = result.get("data")
        if isinstance(data, ReasoningResult):
            return ReasoningOutput(
                answer=data.answer,
                confidence=data.confidence,
                mode=mode,
                steps=[
                    V1ReasoningStep(
                        step_number=s.step_number,
                        description=s.description,
                        conclusion=s.conclusion,
                    )
                    for s in data.steps
                ],
                refinements=0,
                context_used=[context] if context else [],
                memory_hits=0,
                source=data.source,
                total_duration_ms=int(result.get("duration_ms", 0)),
            )

        # Fallback
        return ReasoningOutput(
            answer="Unable to reason about this query",
            confidence=0.1,
            mode=mode,
            source="fallback",
        )

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "ReasoningAgentCompat",
            "call_count": self._call_count,
            "reasoner": self._reasoner.stats,
        }


# ══════════════════════════════════════════════════════════════
#  BusinessLogicAgentCompat
# ══════════════════════════════════════════════════════════════

class BusinessLogicAgentCompat:
    """
    v1-compatible BusinessLogicAgent wrapper around v2 OperationRouter.

    The v1 BusinessLogicAgent was primarily a placeholder; the v2
    OperationRouter handles business operation routing.
    """

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._router = OperationRouter(**kwargs)
        self._call_count = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "BusinessLogicAgentCompat",
            "call_count": self._call_count,
            "router": self._router.stats,
        }
