"""Shared fixture for Phase 8 Intelligence tests."""

import gc
import pytest


@pytest.fixture(scope="module")
def shared_orchestrator():
    """Create a single ZenicOrchestrator shared by all orchestrator tests.

    This avoids loading the fastembed model repeatedly (each instance
    takes ~200MB RAM). The orchestrator is created once per module
    and cleaned up after all tests in the module finish.
    """
    from src.core.orchestrator import ZenicOrchestrator
    orch = ZenicOrchestrator()
    yield orch
    # Force cleanup to free memory
    del orch
    gc.collect()
