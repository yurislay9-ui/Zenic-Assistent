"""
ZENIC-AGENTS - Configuration Package

Facade that re-exports all config functions from loader.py.
Usage: from src.config import load_settings, get_setting, ...
"""

from src.config.loader import (
    load_settings,
    get_setting,
    get_solver_timeout_ms,
    get_solver_fast_timeout_ms,
    get_mcts_config,
    get_k_path_limit,
    get_sandbox_timeout_s,
    get_critical_nodes,
    get_critical_patterns,
)

__all__ = [
    "load_settings",
    "get_setting",
    "get_solver_timeout_ms",
    "get_solver_fast_timeout_ms",
    "get_mcts_config",
    "get_k_path_limit",
    "get_sandbox_timeout_s",
    "get_critical_nodes",
    "get_critical_patterns",
]
