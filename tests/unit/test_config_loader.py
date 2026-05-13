"""
Unit tests for Config Loader

Tests YAML loading, default values, and configuration accessors.
"""

import pytest
from src.config.loader import (
    load_settings, get_solver_timeout_ms, get_solver_fast_timeout_ms,
    get_mcts_config, get_k_path_limit, get_sandbox_timeout_s,
    get_critical_patterns, get_critical_nodes
)


class TestConfigLoader:
    """Tests for configuration loading."""

    def test_load_settings_returns_dict(self):
        """Should return a dictionary."""
        settings = load_settings()
        assert isinstance(settings, dict)

    def test_default_project_dir(self):
        """Should have a default project directory."""
        settings = load_settings()
        assert "project_dir" in settings

    def test_default_engine_limits(self):
        """Should have default engine limits."""
        settings = load_settings()
        assert "engine_limits" in settings
        limits = settings["engine_limits"]
        assert "solver_timeout_ms" in limits
        assert "sandbox_timeout_s" in limits
        assert "mcts_max_depth" in limits
        assert "mcts_max_simulations" in limits

    def test_default_critical_nodes(self):
        """Should have default critical node keywords."""
        settings = load_settings()
        assert "critical_nodes" in settings
        nodes = settings["critical_nodes"]
        assert isinstance(nodes, list)
        assert "auth" in nodes
        assert "crypto" in nodes
        assert "payment" in nodes

    def test_default_critical_patterns(self):
        """Should have default critical patterns."""
        settings = load_settings()
        assert "critical_patterns" in settings
        patterns = settings["critical_patterns"]
        assert isinstance(patterns, list)


class TestConfigAccessors:
    """Tests for configuration accessor functions."""

    def test_get_solver_timeout_ms(self):
        """Should return a positive integer."""
        val = get_solver_timeout_ms()
        assert isinstance(val, int)
        assert val > 0

    def test_get_solver_fast_timeout_ms(self):
        """Should return a positive integer less than surgical timeout."""
        val = get_solver_fast_timeout_ms()
        assert isinstance(val, int)
        assert val > 0
        assert val <= get_solver_timeout_ms()

    def test_get_mcts_config(self):
        """Should return MCTS configuration dict."""
        config = get_mcts_config()
        assert "max_depth" in config
        assert "max_simulations" in config
        assert "timeout_ms" in config
        assert config["max_depth"] > 0
        assert config["max_simulations"] > 0

    def test_get_k_path_limit(self):
        """Should return a positive integer."""
        val = get_k_path_limit()
        assert isinstance(val, int)
        assert val > 0

    def test_get_sandbox_timeout_s(self):
        """Should return a positive number."""
        val = get_sandbox_timeout_s()
        assert isinstance(val, (int, float))
        assert val > 0

    def test_get_critical_patterns(self):
        """Should return a list of patterns."""
        patterns = get_critical_patterns()
        assert isinstance(patterns, list)

    def test_get_critical_nodes(self):
        """Should return a list of keywords."""
        nodes = get_critical_nodes()
        assert isinstance(nodes, list)
        assert len(nodes) > 0

    def test_accessors_accept_settings_arg(self):
        """Accessors should accept an explicit settings dict."""
        settings = load_settings()
        val = get_solver_timeout_ms(settings)
        assert val > 0
