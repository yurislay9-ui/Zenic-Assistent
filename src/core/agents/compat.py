"""
Compatibility adapters: v1 API → v2 agents.

This module provides v1-compatible wrappers around v2 agents so the
orchestrator can use agents without rewriting its call sites.

Every adapter:
  - Delegates to v2 agents internally (execute/run)
  - Exposes the v1 high-level API (classify_with_runner, validate_with_runner, etc.)
  - Translates between v1 schemas (IntentOutput, ValidationOutput, etc.)
    and v2 schemas (IntentResult, SecurityResult, etc.)

Once all orchestrator call sites are migrated to call v2 agents directly,
this module can be deprecated and removed.
"""

from __future__ import annotations

import re
import time
import logging
from typing import Any, Optional

# v2 agents
from .understanding import (
    IntentClassifier,
    EntityExtractor,
    TargetResolver,
    CriticalityScorer,
)
from .reasoning import TemplateReasoner
from .validation import SecurityScanner, SyntaxValidator, RiskCalculator
from .automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    AutomationNamer,
    WorkflowSerializer,
)
from .business import OperationRouter
from .infrastructure import AgentRunner as V2AgentRunner
from .resilience import BaseAgent

# v2 schemas (single source of truth)
from .schemas import (
    AgentResult,
    IntentResult,
    EntityResult,
    TargetResult,
    CriticalityResult,
    SecurityResult,
    SyntaxResult,
    RiskResult,
    ReasoningResult,
    ValidationIssue,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
)

# v1 schema types — still used by the orchestrator call sites
# Migrated from agents/schemas.py to agents/schemas/_v1_compat_schemas.py
from .schemas._v1_compat_schemas import (
    IntentOutput,
    ReasoningOutput,
    ReasoningStep as V1ReasoningStep,
    BusinessOutput,
    AutomationOutput,
    ValidationOutput,
    CriticalityOutput,
)

# Shared utilities (single source of truth)
from src.core.shared.agent_schemas import (
    ValidationIssue as SharedValidationIssue,
    TriggerSpec as SharedTriggerSpec,
    ActionSpec as SharedActionSpec,
    ScheduleSpec as SharedScheduleSpec,
)
from src.core.shared.constants import VALID_INTENT_OPERATIONS, VALID_INTENT_GOALS
# Migrated from agents/intent_shared.py to agents/understanding/intent_utils.py
from .understanding.intent_utils import (
    extract_code_block,
    extract_target_and_language,
    extract_entities,
    infer_criticality,
    infer_template_type,
    OP_KEYWORDS,
    GOAL_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Backward-compatible aliases
VALID_OPERATIONS = VALID_INTENT_OPERATIONS
VALID_GOALS = VALID_INTENT_GOALS


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
        from src.core.shared.contracts import IntentPayload, OperationType, GoalType

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


# ══════════════════════════════════════════════════════════════
#  AutomationAgentCompat
# ══════════════════════════════════════════════════════════════

class AutomationAgentCompat:
    """
    v1-compatible AutomationAgent wrapper around v2 automation agents.

    Provides:
      - design_with_runner(runner, description) -> AutomationOutput
      - to_workflow_dict(output) -> dict
    """

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._trigger_inferrer = TriggerInferrer(**kwargs)
        self._action_inferrer = ActionInferrer(**kwargs)
        self._schedule_parser = ScheduleParser(**kwargs)
        self._namer = AutomationNamer(**kwargs)
        self._serializer = WorkflowSerializer(**kwargs)
        self._call_count = 0

    def design_with_runner(self, runner: Any, description: str,
                           **kwargs) -> AutomationOutput:
        """Design automation using v2 agents."""
        self._call_count += 1

        # Run v2 agents
        trigger_result = self._trigger_inferrer.run(description)
        action_result = self._action_inferrer.run(description)
        schedule_result = self._schedule_parser.run(description)
        name_result = self._namer.run(description)

        # Extract data from v2 results
        triggers = self._extract_triggers(trigger_result)
        actions = self._extract_actions(action_result)
        schedule = self._extract_schedule(schedule_result)
        name = self._extract_name(name_result)

        return AutomationOutput(
            name=name,
            triggers=triggers,
            actions=actions,
            schedule=schedule,
            conditions=[],
            description=description[:200],
            source="deterministic",
        )

    def to_workflow_dict(self, output: AutomationOutput) -> dict:
        """Convert AutomationOutput to workflow dict."""
        return {
            "name": output.name,
            "triggers": [
                {"type": t.type, "config": t.config, "description": t.description}
                for t in output.triggers
            ],
            "actions": [
                {"type": a.type, "config": a.config, "description": a.description}
                for a in output.actions
            ],
            "schedule": {
                "type": output.schedule.type,
                "cron": output.schedule.cron_expression,
            },
            "source": output.source,
        }

    def _extract_triggers(self, result: dict) -> list[SharedTriggerSpec]:
        """Extract triggers from v2 TriggerInferrer result."""
        data = result.get("data")
        if isinstance(data, dict) and "triggers" in data:
            raw = data["triggers"]
            if isinstance(raw, list):
                return [
                    t if isinstance(t, SharedTriggerSpec) else SharedTriggerSpec(
                        type=t.get("type", "manual") if isinstance(t, dict) else "manual",
                        config=t.get("config", {}) if isinstance(t, dict) else {},
                        description=t.get("description", "") if isinstance(t, dict) else str(t),
                    )
                    for t in raw
                ]
        return [SharedTriggerSpec(type="manual", description= "Inferred from user description")]

    def _extract_actions(self, result: dict) -> list[SharedActionSpec]:
        """Extract actions from v2 ActionInferrer result."""
        data = result.get("data")
        if isinstance(data, dict) and "actions" in data:
            raw = data["actions"]
            if isinstance(raw, list):
                return [
                    a if isinstance(a, SharedActionSpec) else SharedActionSpec(
                        type=a.get("type", "log") if isinstance(a, dict) else "log",
                        config=a.get("config", {}) if isinstance(a, dict) else {},
                        description=a.get("description", "") if isinstance(a, dict) else str(a),
                    )
                    for a in raw
                ]
        return [SharedActionSpec(type="log", description="Default log action")]

    def _extract_schedule(self, result: dict) -> SharedScheduleSpec:
        """Extract schedule from v2 ScheduleParser result."""
        data = result.get("data")
        if isinstance(data, dict):
            return SharedScheduleSpec(
                type=data.get("type", "manual"),
                cron=data.get("cron", ""),
                interval_seconds=data.get("interval_seconds", 0),
                description=data.get("description", ""),
            )
        return SharedScheduleSpec()

    def _extract_name(self, result: dict) -> str:
        """Extract name from v2 AutomationNamer result."""
        data = result.get("data")
        if isinstance(data, dict):
            return data.get("name", data.get("slug", "unnamed_automation"))
        if isinstance(data, str):
            return data
        return "unnamed_automation"

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "AutomationAgentCompat",
            "call_count": self._call_count,
        }


# ══════════════════════════════════════════════════════════════
#  ValidationAgentCompat
# ══════════════════════════════════════════════════════════════

class ValidationAgentCompat:
    """
    v1-compatible ValidationAgent wrapper around v2 validation agents.

    Provides:
      - validate_with_runner(runner, target, content, rules, language) -> ValidationOutput
    """

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._security_scanner = SecurityScanner(**kwargs)
        self._syntax_validator = SyntaxValidator(**kwargs)
        self._risk_calculator = RiskCalculator(**kwargs)
        self._call_count = 0

    def validate_with_runner(self, runner: Any, target: str, content: str,
                             rules: list[str] = None,
                             language: str = "python") -> ValidationOutput:
        """Validate using v2 agents."""
        self._call_count += 1
        rules = rules or ["security", "quality"]

        all_issues: list[SharedValidationIssue] = []

        # Security scan
        if "security" in rules and content:
            sec_result = self._security_scanner.run({"code": content, "language": language})
            sec_data = sec_result.get("data")
            if isinstance(sec_data, SecurityResult):
                all_issues.extend([
                    SharedValidationIssue(
                        severity=t.severity,
                        code=t.code,
                        message=t.message,
                        line=t.line,
                        suggestion=t.suggestion,
                    )
                    for t in sec_data.threats
                ])

        # Syntax validation
        if "quality" in rules and content:
            syn_result = self._syntax_validator.run({"code": content, "language": language})
            syn_data = syn_result.get("data")
            if isinstance(syn_data, SyntaxResult):
                all_issues.extend([
                    SharedValidationIssue(
                        severity=e.severity,
                        code=e.code,
                        message=e.message,
                        line=e.line,
                        suggestion=e.suggestion,
                    )
                    for e in syn_data.errors
                ])

        # Chain validation
        if target == "chain" and content:
            from .validation import ChainValidator
            chain_val = ChainValidator()
            chain_result = chain_val.run({"description": content})
            chain_data = chain_result.get("data")
            if isinstance(chain_data, dict):
                incompat = chain_data.get("incompatibilities", [])
                for inc in incompat:
                    all_issues.append(SharedValidationIssue(
                        severity="warning",
                        code="chain_incompatibility",
                        message=str(inc),
                    ))

        # Risk calculation
        risk_score = 0.0
        if content:
            risk_result = self._risk_calculator.run({"issues": all_issues, "code": content})
            risk_data = risk_result.get("data")
            if isinstance(risk_data, RiskResult):
                risk_score = risk_data.score

        # Build suggestions
        suggestions = [
            i.suggestion for i in all_issues if i.suggestion
        ]

        is_valid = not any(i.severity == "error" for i in all_issues)

        return ValidationOutput(
            is_valid=is_valid,
            issues=all_issues,
            suggestions=suggestions,
            risk_score=risk_score,
            source="deterministic",
        )

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "ValidationAgentCompat",
            "call_count": self._call_count,
            "security_scanner": self._security_scanner.stats,
        }


# ══════════════════════════════════════════════════════════════
#  AgentRunnerCompat
# ══════════════════════════════════════════════════════════════

class AgentRunnerCompat:
    """
    v1-compatible AgentRunner wrapper around v2 infrastructure.

    The v1 AgentRunner was LLM-centric (cache → LLM → parse → fallback).
    The v2 AgentRunner is a registry-based executor.

    This compat layer:
      - Accepts mini_ai, semantic_engine, smart_memory (v1 constructor)
      - Provides v1 stats interface
      - Internally uses v2 AgentRunner for registered agents
    """

    def __init__(self, mini_ai=None, semantic_engine=None,
                 smart_memory=None, enable_cache: bool = True,
                 **kwargs) -> None:
        self._mini_ai = mini_ai
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        self._v2_runner = V2AgentRunner()
        self._cache = None
        self._enable_cache = enable_cache
        self._total_calls = 0
        self._cache_hits = 0
        self._llm_calls = 0
        self._fallback_calls = 0

        if enable_cache:
            from .infrastructure.cache import AgentCache
            self._cache = AgentCache()
            if semantic_engine and semantic_engine.is_loaded:
                self._cache.set_semantic_engine(semantic_engine)

    def run(self, agent: Any, input_data: Any) -> AgentResult:
        """
        Execute an agent. For v2 BaseAgent instances, use v2 runner.
        For v1 agents (with build_prompt/parse_response), use legacy path.
        """
        self._total_calls += 1

        # Check cache
        if self._enable_cache and self._cache is not None:
            cached = self._cache.get(agent.name, input_data)
            if cached is not None:
                self._cache_hits += 1
                return AgentResult(
                    success=True, data=cached,
                    source="cache", duration_ms=0, cache_hit=True,
                )

        # v2 BaseAgent: use v2 runner
        if isinstance(agent, BaseAgent):
            result_dict = agent.run(input_data)
            success = result_dict.get("success", False)
            data = result_dict.get("data")
            source = result_dict.get("source", "deterministic")
            duration_ms = result_dict.get("duration_ms", 0.0)

            if success and self._enable_cache and self._cache is not None:
                self._cache.put(agent.name, input_data, data)

            return AgentResult(
                success=success,
                data=data,
                source=source,
                duration_ms=duration_ms,
            )

        # Legacy v1 agent: delegate to its run method
        if hasattr(agent, 'build_prompt') and hasattr(agent, 'parse_response'):
            return self._run_legacy_agent(agent, input_data)

        return AgentResult(
            success=False,
            source="error",
            error=f"Unknown agent type: {type(agent)}",
        )

    def _run_legacy_agent(self, agent: Any, input_data: Any) -> AgentResult:
        """Run a legacy v1 agent (build_prompt/parse_response pattern)."""
        if self._mini_ai and self._mini_ai.is_loaded:
            try:
                system_prompt, user_prompt = agent.build_prompt(input_data)
                raw_response = self._mini_ai._call_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=600,
                )
                if raw_response:
                    parsed = agent.parse_response(raw_response, input_data)
                    if parsed and agent.validate_output(parsed):
                        self._llm_calls += 1
                        if self._enable_cache and self._cache is not None:
                            self._cache.put(agent.name, input_data, parsed)
                        return AgentResult(
                            success=True, data=parsed,
                            source="llm", duration_ms=0,
                        )
            except Exception as e:
                logger.debug(f"AgentRunnerCompat: LLM call failed: {e}")

        # Fallback
        self._fallback_calls += 1
        try:
            fallback_result = agent.fallback(input_data)
            return AgentResult(
                success=True, data=fallback_result,
                source="fallback", duration_ms=0,
            )
        except Exception as e:
            return AgentResult(
                success=False, source="error", error=str(e),
            )

    def clear_cache(self) -> None:
        if self._cache:
            self._cache.clear()

    def update_engines(self, mini_ai=None, semantic_engine=None,
                       smart_memory=None) -> None:
        if mini_ai is not None:
            self._mini_ai = mini_ai
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._total_calls,
            "cache_hits": self._cache_hits,
            "llm_calls": self._llm_calls,
            "fallback_calls": self._fallback_calls,
            "cache_hit_rate": self._cache_hits / max(self._total_calls, 1),
            "cache_size": len(self._cache) if self._cache else 0,
        }

    @property
    def cache(self):
        return self._cache

    @property
    def mini_ai(self):
        return self._mini_ai


# ══════════════════════════════════════════════════════════════
#  Convenience re-exports
# ══════════════════════════════════════════════════════════════

__all__ = [
    "SurgicalAgentCompat",
    "ReasoningAgentCompat",
    "BusinessLogicAgentCompat",
    "AutomationAgentCompat",
    "ValidationAgentCompat",
    "AgentRunnerCompat",
]
