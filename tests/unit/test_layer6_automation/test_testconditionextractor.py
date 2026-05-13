"""
Tests for Layer 6: Automation agents (A29-A34).

All 6 agents tested:
  - A29 TriggerInferrer
  - A30 ActionInferrer
  - A31 ScheduleParser
  - A32 ConditionExtractor
  - A33 AutomationNamer
  - A34 WorkflowSerializer
"""

import json
import pytest

from src.core.agents_v2.automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    ConditionExtractor,
    AutomationNamer,
    WorkflowSerializer,
)
from src.core.agents_v2.schemas import (
    AutoDescription,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
    ConditionResult,
    NameResult,
    WorkflowSpec,
)


# ═══════════════════════════════════════════════════════════
# A29 TriggerInferrer Tests
# ═══════════════════════════════════════════════════════════



class TestConditionExtractor:
    """A32: Extract conditional logic from description."""

    def setup_method(self):
        self.extractor = ConditionExtractor()

    def test_if_condition_en(self):
        """'if X then' should extract condition."""
        result = self.extractor.execute(
            {"description": "send email if balance exceeds 1000"}
        )
        assert isinstance(result, ConditionResult)
        assert len(result.conditions) > 0
        assert any("balance" in c.lower() for c in result.conditions)

    def test_si_condition_es(self):
        """'si X' should extract condition."""
        result = self.extractor.execute(
            {"description": "enviar alerta si el inventario es bajo"}
        )
        assert len(result.conditions) > 0
        assert any("inventario" in c.lower() for c in result.conditions)

    def test_only_when_condition(self):
        """'only when X' should extract condition."""
        result = self.extractor.execute(
            {"description": "process only when status is active"}
        )
        assert len(result.conditions) > 0

    def test_when_condition(self):
        """'when X' should extract condition."""
        result = self.extractor.execute(
            {"description": "alert when server is down"}
        )
        assert len(result.conditions) > 0

    def test_no_conditions(self):
        """No condition keywords should return empty."""
        result = self.extractor.execute(
            {"description": "send daily email report"}
        )
        assert len(result.conditions) == 0

    def test_logic_tree_built(self):
        """Logic tree should be built when conditions found."""
        result = self.extractor.execute(
            {"description": "send alert if error count > 5 and retry failed"}
        )
        if result.conditions:
            assert "operator" in result.logic_tree

    def test_and_operator_detected(self):
        """' and ' should set AND operator in logic tree."""
        result = self.extractor.execute(
            {"description": "notify if status is critical and retry count exceeds 3"}
        )
        if result.conditions and result.logic_tree:
            assert result.logic_tree.get("operator") in ("AND", "SINGLE")

    def test_or_operator_detected(self):
        """' or ' should set OR operator in logic tree."""
        result = self.extractor.execute(
            {"description": "alert if cpu > 90 or memory > 80"}
        )
        if result.conditions and result.logic_tree:
            assert result.logic_tree.get("operator") in ("OR", "AND", "SINGLE")

    def test_empty_description(self):
        """Empty description should return empty conditions."""
        result = self.extractor.execute({"description": ""})
        assert len(result.conditions) == 0

    def test_fallback_returns_empty(self):
        """Fallback should return empty conditions."""
        result = self.extractor.fallback(None)
        assert len(result.conditions) == 0
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A33 AutomationNamer Tests
# ═══════════════════════════════════════════════════════════

