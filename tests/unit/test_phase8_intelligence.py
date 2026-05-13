"""
ZENIC-AGENTS - Phase 8 Intelligence Tests

Tests for the Phase 8 components.
"""

import gc
import pytest


# ============================================================
#  Shared fixture (also in test_phase8_parts/conftest.py for direct sub-module runs)
# ============================================================

@pytest.fixture(scope="module")
def shared_orchestrator():
    """Create a single ZenicOrchestrator shared by all orchestrator tests."""
    from src.core.orchestrator import ZenicOrchestrator
    orch = ZenicOrchestrator()
    yield orch
    del orch
    gc.collect()


from .test_phase8_parts import *  # noqa: F401,F403
