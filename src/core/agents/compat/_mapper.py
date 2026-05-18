"""
v1-compatible mapper classes: Automation and Validation.
"""

from __future__ import annotations

from typing import Any

# v2 agents
from ..automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    AutomationNamer,
    WorkflowSerializer,
)
from ..validation import SecurityScanner, SyntaxValidator, RiskCalculator

# v2 schemas
from ..schemas import SecurityResult, SyntaxResult, RiskResult

# v1 schema types
from ..schemas._v1_compat_schemas import (
    AutomationOutput,
    ValidationOutput,
)

# Shared utilities
from src.core.shared.agent_schemas import (
    ValidationIssue as SharedValidationIssue,
    TriggerSpec as SharedTriggerSpec,
    ActionSpec as SharedActionSpec,
    ScheduleSpec as SharedScheduleSpec,
)

# Local compat types
from ._types import logger


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
            from ..validation import ChainValidator
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
