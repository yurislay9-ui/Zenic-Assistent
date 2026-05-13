"""
Tests for ContextAgent constructor, wiring, CABLEs 1-3 (collect, score, compress).
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.context_agent import (
    ContextAgent,
    ContextOutput,
    ContextEntry,
)
from src.core.agents.schemas import IntentOutput


# ============================================================
#  TEST: Constructor y wiring
# ============================================================

class TestContextAgentInit:

    def test_init_default(self):
        agent = ContextAgent()
        assert agent.name == "context"
        assert agent._semantic_engine is None
        assert agent._smart_memory is None
        assert agent._shared_context_cache == {}

    def test_init_with_engines(self, mock_semantic_engine, mock_smart_memory):
        agent = ContextAgent(
            semantic_engine=mock_semantic_engine,
            smart_memory=mock_smart_memory,
        )
        assert agent._semantic_engine is mock_semantic_engine
        assert agent._smart_memory is mock_smart_memory

    def test_wire(self, context_agent):
        new_sem = MagicMock()
        new_mem = MagicMock()
        context_agent.wire(semantic_engine=new_sem, smart_memory=new_mem)
        assert context_agent._semantic_engine is new_sem
        assert context_agent._smart_memory is new_mem


# ============================================================
#  TEST: CABLE 1 — Recopilar entradas de memoria
# ============================================================

class TestCable1CollectEntries:

    def test_collects_working_memory(self, context_agent, mock_smart_memory):
        entries = context_agent._collect_entries("build API", "CREATE", "FEATURE_ADD")
        assert len(entries) >= 5

    def test_collects_long_term_memory(self, context_agent, mock_smart_memory, mock_semantic_engine):
        entries = context_agent._collect_entries("build API", "CREATE", "FEATURE_ADD")
        sources = [e.source for e in entries]
        assert "working" in sources
        assert "long_term" in sources

    def test_collects_procedural_memory(self, context_agent, mock_smart_memory):
        entries = context_agent._collect_entries("build API", "CREATE", "FEATURE_ADD")
        sources = [e.source for e in entries]
        assert "procedural" in sources

    def test_handles_no_memory(self):
        agent = ContextAgent()
        entries = agent._collect_entries("test", "SEARCH", "FEATURE_ADD")
        assert entries == []

    def test_handles_memory_error(self, context_agent, mock_smart_memory):
        mock_smart_memory._working_memory = [object()]
        entries = context_agent._collect_entries("test", "SEARCH", "FEATURE_ADD")
        assert isinstance(entries, list)


# ============================================================
#  TEST: CABLE 2 — Scoring de relevancia
# ============================================================

class TestCable2ScoreEntries:

    def test_scores_by_operation_relevance(self, context_agent):
        entries = [
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.5, recency=1.0, content="test1"),
            ContextEntry(operation="DEBUG", goal="BUG_FIX", importance=0.5, recency=1.0, content="test2"),
            ContextEntry(operation="OPTIMIZE", goal="PERFORMANCE", importance=0.5, recency=1.0, content="test3"),
        ]
        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        assert scored[0].operation == "CREATE"

    def test_scores_by_recency(self, context_agent):
        entries = [
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.5, recency=0.3, content="old"),
            ContextEntry(operation="SEARCH", goal="FEATURE_ADD", importance=0.5, recency=1.0, content="new"),
        ]
        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        assert all(e.relevance_score > 0 for e in scored)
        assert scored[0].relevance_score >= scored[1].relevance_score

    def test_scores_by_importance(self, context_agent):
        entries = [
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.9, recency=0.5, content="important"),
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.2, recency=0.5, content="unimportant"),
        ]
        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        assert scored[0].importance > scored[1].importance

    def test_combined_scoring(self, context_agent):
        entries = [
            ContextEntry(operation="DEBUG", goal="BUG_FIX", importance=0.9, recency=0.2, content="old debug"),
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.5, recency=1.0, content="new create"),
        ]
        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        assert scored[0].relevance_score > 0


# ============================================================
#  TEST: CABLE 3 — Compresión adaptativa
# ============================================================

class TestCable3Compression:

    def test_compress_empty_entries(self, context_agent):
        result, count = context_agent._compress_entries([], 200, "CREATE", "FEATURE_ADD")
        assert result == ""
        assert count == 0

    def test_compress_fits_budget(self, context_agent):
        entries = [
            ContextEntry(content="Short entry", token_estimate=3, relevance_score=0.8,
                        operation="CREATE", goal="FEATURE_ADD"),
        ]
        result, count = context_agent._compress_entries(entries, 200, "CREATE", "FEATURE_ADD")
        assert count == 1
        assert "Short entry" in result

    def test_compress_truncates_too_long(self, context_agent):
        entries = [
            ContextEntry(content="A" * 500, token_estimate=200, relevance_score=0.9,
                        operation="CREATE", goal="FEATURE_ADD"),
        ]
        result, count = context_agent._compress_entries(entries, 50, "CREATE", "FEATURE_ADD")
        assert count == 1
        assert len(result) <= 50 * 4 + 10

    def test_compress_selects_by_relevance(self, context_agent):
        entries = [
            ContextEntry(content="High relevance entry", token_estimate=100,
                        relevance_score=0.9, operation="CREATE", goal="FEATURE_ADD"),
            ContextEntry(content="Low relevance entry", token_estimate=100,
                        relevance_score=0.2, operation="SEARCH", goal="FEATURE_ADD"),
        ]
        result, count = context_agent._compress_entries(entries, 110, "CREATE", "FEATURE_ADD")
        assert count == 1
        assert "High relevance" in result
