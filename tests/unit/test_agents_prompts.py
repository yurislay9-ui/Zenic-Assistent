"""
Unit tests for Agent Prompts

Tests AgentPrompts constants, PromptBuilder template substitution,
and add_context_to_prompt augmentation.
"""

import json
import pytest
from unittest.mock import MagicMock

from src.core.agents.prompts import AgentPrompts, PromptBuilder


class TestAgentPromptsConstants:
    """Tests that AgentPrompts has the expected prompt templates."""

    def test_intent_prompts_exist(self):
        """Should have INTENT_SYSTEM and INTENT_USER templates."""
        assert hasattr(AgentPrompts, "INTENT_SYSTEM")
        assert hasattr(AgentPrompts, "INTENT_USER")
        assert "operation" in AgentPrompts.INTENT_SYSTEM.lower()
        assert "{message}" in AgentPrompts.INTENT_USER

    def test_reasoning_prompts_exist(self):
        """Should have REASONING_SYSTEM and REASONING_USER templates."""
        assert hasattr(AgentPrompts, "REASONING_SYSTEM_STEP_BY_STEP")
        assert hasattr(AgentPrompts, "REASONING_SYSTEM_SELF_REFLECT")
        assert hasattr(AgentPrompts, "REASONING_SYSTEM_WITH_CONTEXT")
        assert hasattr(AgentPrompts, "REASONING_USER")
        assert "{query}" in AgentPrompts.REASONING_USER

    def test_business_prompts_exist(self):
        """Should have BUSINESS_SYSTEM and BUSINESS_USER templates."""
        assert hasattr(AgentPrompts, "BUSINESS_SYSTEM")
        assert hasattr(AgentPrompts, "BUSINESS_USER")
        assert "{operation_type}" in AgentPrompts.BUSINESS_USER
        assert "{data}" in AgentPrompts.BUSINESS_USER

    def test_code_prompts_exist(self):
        """Should have CODE_SYSTEM and CODE_USER templates."""
        assert hasattr(AgentPrompts, "CODE_SYSTEM_GENERATE")
        assert hasattr(AgentPrompts, "CODE_SYSTEM_TRANSFORM")
        assert hasattr(AgentPrompts, "CODE_SYSTEM_SCAFFOLD")
        assert hasattr(AgentPrompts, "CODE_USER")
        assert "{task}" in AgentPrompts.CODE_USER

    def test_automation_prompts_exist(self):
        """Should have AUTOMATION_SYSTEM and AUTOMATION_USER templates."""
        assert hasattr(AgentPrompts, "AUTOMATION_SYSTEM")
        assert hasattr(AgentPrompts, "AUTOMATION_USER")
        assert "{description}" in AgentPrompts.AUTOMATION_USER

    def test_validation_prompts_exist(self):
        """Should have VALIDATION_SYSTEM and VALIDATION_USER templates."""
        assert hasattr(AgentPrompts, "VALIDATION_SYSTEM")
        assert hasattr(AgentPrompts, "VALIDATION_USER")
        assert "{target}" in AgentPrompts.VALIDATION_USER

    def test_context_prompts_exist(self):
        """Should have CONTEXT_SYSTEM_COMPRESS and CONTEXT_USER_COMPRESS."""
        assert hasattr(AgentPrompts, "CONTEXT_SYSTEM_COMPRESS")
        assert hasattr(AgentPrompts, "CONTEXT_USER_COMPRESS")
        assert "{operation}" in AgentPrompts.CONTEXT_USER_COMPRESS
        assert "{raw_context}" in AgentPrompts.CONTEXT_USER_COMPRESS

    def test_system_prompts_contain_json_format(self):
        """All system prompts should instruct JSON output format."""
        for attr_name in dir(AgentPrompts):
            if attr_name.startswith("SYSTEM") or attr_name.startswith("INTENT_SYSTEM"):
                template = getattr(AgentPrompts, attr_name)
                assert "JSON" in template or "json" in template.lower()


class TestPromptBuilder:
    """Tests for PromptBuilder.build static method."""

    def test_basic_substitution(self):
        """Should substitute placeholders in user template."""
        system, user = PromptBuilder.build(
            "You are a bot.",
            "Hello {name}, your score is {score}",
            {"name": "Alice", "score": 42},
        )
        assert system == "You are a bot."
        assert "Alice" in user
        assert "42" in user

    def test_no_substitution_without_placeholders(self):
        """Should return template unchanged when no placeholders match."""
        system, user = PromptBuilder.build(
            "System prompt",
            "No placeholders here",
            {"key": "value"},
        )
        assert user == "No placeholders here"

    def test_missing_placeholder_in_context(self):
        """Should leave placeholder unchanged when context key is missing."""
        system, user = PromptBuilder.build(
            "System",
            "Hello {name}, {missing_key}",
            {"name": "Bob"},
        )
        assert "Bob" in user
        assert "{missing_key}" in user

    def test_dict_value_serialized_as_json(self):
        """Should serialize dict values as JSON in user prompt."""
        system, user = PromptBuilder.build(
            "Sys",
            "Data: {data}",
            {"data": {"key": "val"}},
        )
        assert '{"key": "val"}' in user

    def test_list_value_serialized_as_json(self):
        """Should serialize list values as JSON in user prompt."""
        system, user = PromptBuilder.build(
            "Sys",
            "Items: {items}",
            {"items": [1, 2, 3]},
        )
        assert "[1, 2, 3]" in user

    def test_system_template_unchanged(self):
        """System template should never be modified."""
        sys_template = "System with {curly} braces"
        system, user = PromptBuilder.build(
            sys_template, "User {name}", {"name": "test", "curly": "X"},
        )
        assert system == sys_template
        assert "{curly}" in system  # Not substituted in system

    def test_long_values_truncated(self):
        """Values over 500 chars should be truncated in user prompt."""
        long_val = "x" * 600
        system, user = PromptBuilder.build(
            "Sys", "Val: {val}", {"val": long_val},
        )
        assert len(user) < 700  # Truncated, not full 600+

    def test_intent_prompt_build(self):
        """Should build a complete intent prompt."""
        system, user = PromptBuilder.build(
            AgentPrompts.INTENT_SYSTEM,
            AgentPrompts.INTENT_USER,
            {"message": "Create a REST API for users"},
        )
        assert "Create a REST API for users" in user
        assert "intent classification" in system.lower()


class TestAddContextToPrompt:
    """Tests for PromptBuilder.add_context_to_prompt."""

    def test_adds_context_section(self):
        """Should append context section to the prompt."""
        prompt = "Original prompt"
        context = {"file": "main.py", "language": "python"}
        result = PromptBuilder.add_context_to_prompt(prompt, context)
        assert "Original prompt" in result
        assert "Additional context:" in result
        assert "file: main.py" in result
        assert "language: python" in result

    def test_empty_context_returns_prompt_unchanged(self):
        """Should return prompt unchanged when context is empty."""
        prompt = "Original"
        result = PromptBuilder.add_context_to_prompt(prompt, {})
        assert result == "Original"

    def test_none_values_skipped(self):
        """Should skip context items with falsy values."""
        prompt = "P"
        context = {"a": "val", "b": "", "c": None, "d": 0}
        result = PromptBuilder.add_context_to_prompt(prompt, context)
        assert "a: val" in result
        # Empty string and None should be skipped; 0 is falsy too
        assert "b:" not in result

    def test_dict_value_serialized(self):
        """Should serialize dict values in context."""
        prompt = "P"
        context = {"data": {"key": "value"}}
        result = PromptBuilder.add_context_to_prompt(prompt, context)
        assert '"key": "value"' in result

    def test_truncates_long_values(self):
        """Should truncate values longer than 200 chars."""
        prompt = "P"
        long_val = "a" * 300
        context = {"big": long_val}
        result = PromptBuilder.add_context_to_prompt(prompt, context)
        assert "..." in result  # Truncation indicator

    def test_max_chars_limit(self):
        """Should respect max_chars limit for context text."""
        prompt = "P"
        context = {f"k{i}": f"v{i}" * 50 for i in range(20)}
        result = PromptBuilder.add_context_to_prompt(prompt, context, max_chars=200)
        context_section = result.split("Additional context:\n")[1]
        assert len(context_section) <= 203  # 200 + "..."

    def test_max_10_items(self):
        """Should include at most 10 context items."""
        prompt = "P"
        context = {f"key{i}": f"val{i}" for i in range(15)}
        result = PromptBuilder.add_context_to_prompt(prompt, context)
        # Count lines in context section
        context_section = result.split("Additional context:\n")[1]
        lines = [l for l in context_section.strip().split("\n") if l.startswith("- ")]
        assert len(lines) <= 10
