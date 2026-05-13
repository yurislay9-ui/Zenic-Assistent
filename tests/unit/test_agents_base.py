"""
Unit tests for BaseAgent

Tests lifecycle, stats tracking, JSON extraction, list extraction,
text cleaning, and thread safety.
"""

import json
import threading
import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.base import BaseAgent, AgentResult


# Concrete subclass for testing (BaseAgent is abstract)
class DummyAgent(BaseAgent):
    """Minimal concrete agent for testing."""

    def build_prompt(self, input_data):
        return ("system prompt", f"user: {input_data}")

    def parse_response(self, raw_response, input_data):
        return {"parsed": raw_response}

    def fallback(self, input_data):
        return {"fallback": input_data}


class TestAgentResult:
    """Tests for the AgentResult data class."""

    def test_default_values(self):
        """Should have sensible defaults."""
        result = AgentResult()
        assert result.success is False
        assert result.data is None
        assert result.source in ("deterministic", "fallback")  # v2 uses "deterministic", legacy used "fallback"
        assert result.error == ""
        assert result.duration_ms == 0
        assert result.cache_hit is False

    def test_custom_values(self):
        """Should accept custom values."""
        result = AgentResult(
            success=True, data={"key": "val"}, source="llm",
            duration_ms=42, cache_hit=True,
        )
        assert result.success is True
        assert result.data == {"key": "val"}
        assert result.source == "llm"
        assert result.duration_ms == 42
        assert result.cache_hit is True

    def test_repr(self):
        """Should produce a readable repr string."""
        result = AgentResult(success=True, source="llm", duration_ms=100)
        r = repr(result)
        assert "success=True" in r
        assert "llm" in r  # source should appear in repr
        assert "100" in r  # duration should appear in repr


class TestBaseAgentInit:
    """Tests for BaseAgent initialization and basic properties."""

    def test_default_name(self):
        """Should use 'base' as the default name."""
        agent = DummyAgent()
        assert agent.name == "base"

    def test_custom_name(self):
        """Should accept a custom name."""
        agent = DummyAgent(name="my_agent")
        assert agent.name == "my_agent"

    def test_initial_stats(self):
        """Stats should be zeroed on init."""
        agent = DummyAgent(name="test")
        stats = agent.stats
        assert stats["total_calls"] == 0
        assert stats["llm_success"] == 0
        assert stats["fallback_calls"] == 0
        assert stats["cache_hits"] == 0
        assert stats["avg_duration_ms"] == 0
        assert stats["last_error"] == ""


class TestBaseAgentStats:
    """Tests for _update_stats and stats property."""

    def test_update_stats_llm(self):
        """Should track LLM source correctly."""
        agent = DummyAgent()
        agent._update_stats("llm", 100)
        stats = agent.stats
        assert stats["total_calls"] == 1
        assert stats["llm_success"] == 1
        assert stats["llm_rate"] == 1.0

    def test_update_stats_fallback(self):
        """Should track fallback source correctly."""
        agent = DummyAgent()
        agent._update_stats("fallback", 50)
        stats = agent.stats
        assert stats["total_calls"] == 1
        assert stats["fallback_calls"] == 1
        assert stats["fallback_rate"] == 1.0

    def test_update_stats_cache(self):
        """Should track cache source correctly."""
        agent = DummyAgent()
        agent._update_stats("cache", 1)
        stats = agent.stats
        assert stats["total_calls"] == 1
        assert stats["cache_hits"] == 1

    def test_update_stats_with_error(self):
        """Should store the last error message."""
        agent = DummyAgent()
        agent._update_stats("fallback", 10, error="timeout")
        assert agent.stats["last_error"] == "timeout"

    def test_avg_duration_accumulates(self):
        """Should accumulate duration across calls."""
        agent = DummyAgent()
        agent._update_stats("llm", 100)
        agent._update_stats("llm", 200)
        assert agent.stats["avg_duration_ms"] == 150.0

    def test_rates_with_zero_calls(self):
        """Should avoid division by zero in rates."""
        agent = DummyAgent()
        stats = agent.stats
        assert stats["llm_rate"] == 0.0
        assert stats["fallback_rate"] == 0.0


class TestBaseAgentValidateOutput:
    """Tests for validate_output."""

    def test_non_none_is_valid(self):
        """Should return True for any non-None output."""
        agent = DummyAgent()
        assert agent.validate_output("hello") is True
        assert agent.validate_output(42) is True
        assert agent.validate_output({}) is True

    def test_none_is_invalid(self):
        """Should return False for None."""
        agent = DummyAgent()
        assert agent.validate_output(None) is False


class TestBaseAgentExtractJson:
    """Tests for the extract_json static method."""

    def test_direct_json_object(self):
        """Should parse a plain JSON object."""
        text = '{"key": "value"}'
        result = BaseAgent.extract_json(text)
        assert result == {"key": "value"}

    def test_markdown_code_block(self):
        """Should extract JSON from a markdown code block."""
        text = 'Here is the result:\n```json\n{"x": 1}\n```'
        result = BaseAgent.extract_json(text)
        assert result == {"x": 1}

    def test_embedded_json_in_text(self):
        """Should extract JSON embedded in surrounding text."""
        text = 'The answer is {"name": "test", "val": 42} and done'
        result = BaseAgent.extract_json(text)
        assert result == {"name": "test", "val": 42}

    def test_json_array(self):
        """Should extract a JSON array."""
        text = 'Items: [1, 2, 3] end'
        result = BaseAgent.extract_json(text)
        assert result == [1, 2, 3]

    def test_no_json_returns_none(self):
        """Should return None when no JSON is found."""
        text = "just plain text with no json"
        result = BaseAgent.extract_json(text)
        assert result is None

    def test_nested_json_object(self):
        """Should extract nested JSON objects."""
        text = 'result {"outer": {"inner": 1}} done'
        result = BaseAgent.extract_json(text)
        assert result == {"outer": {"inner": 1}}


class TestBaseAgentExtractList:
    """Tests for the extract_list static method."""

    def test_numbered_items(self):
        """Should extract numbered list items."""
        text = "1. first\n2. second\n3. third"
        result = BaseAgent.extract_list(text)
        assert result == ["first", "second", "third"]

    def test_bullet_items(self):
        """Should extract bullet list items."""
        text = "- alpha\n- beta\n* gamma"
        result = BaseAgent.extract_list(text)
        assert result == ["alpha", "beta", "gamma"]

    def test_mixed_items(self):
        """Should extract both numbered and bullet items."""
        text = "1. first\n- second\n2. third"
        result = BaseAgent.extract_list(text)
        assert result == ["first", "second", "third"]

    def test_empty_text(self):
        """Should return empty list for empty text."""
        result = BaseAgent.extract_list("")
        assert result == []

    def test_plain_text_no_list(self):
        """Should return empty list when no list markers found."""
        result = BaseAgent.extract_list("just some plain text")
        assert result == []


class TestBaseAgentCleanLlmText:
    """Tests for the clean_llm_text static method."""

    def test_removes_think_blocks(self):
        """Should remove Qwen3-style think blocks."""
        text = "<think reasoning>internal thought</think > actual output"
        result = BaseAgent.clean_llm_text(text)
        assert "internal thought" not in result
        assert "actual output" in result

    def test_removes_markdown_fences(self):
        """Should remove markdown code fences."""
        text = "```python\ncode here\n```"
        result = BaseAgent.clean_llm_text(text)
        assert "```" not in result
        assert "code here" in result

    def test_removes_bold_markers(self):
        """Should remove markdown bold markers."""
        text = "This is **bold** text"
        result = BaseAgent.clean_llm_text(text)
        assert "**bold**" not in result
        assert "bold" in result

    def test_collapses_multiple_newlines(self):
        """Should collapse 3+ newlines into 2."""
        text = "para1\n\n\n\npara2"
        result = BaseAgent.clean_llm_text(text)
        assert "\n\n\n" not in result

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        text = "  hello  "
        result = BaseAgent.clean_llm_text(text)
        assert result == "hello"


class TestBaseAgentThreadSafety:
    """Tests for thread safety of stats tracking."""

    def test_concurrent_update_stats(self):
        """Should handle concurrent _update_stats calls without data corruption."""
        agent = DummyAgent()
        errors = []

        def worker(source, duration):
            try:
                for _ in range(100):
                    agent._update_stats(source, duration)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=("llm", 10)),
            threading.Thread(target=worker, args=("fallback", 20)),
            threading.Thread(target=worker, args=("cache", 1)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = agent.stats
        assert stats["total_calls"] == 300
        assert stats["llm_success"] == 100
        assert stats["fallback_calls"] == 100
        assert stats["cache_hits"] == 100
