"""
ZENIC-AGENTS — Global Pytest Configuration (Phase 5 Fix)

Ensures 100% deterministic behavior in ALL tests by:
1. Setting a fixed global seed before each test
2. Installing uuid.uuid4() patch (covers all 95+ files)
3. Installing random.choice/uniform/etc. patch (covers bare random calls)
4. Installing time.time() patch (deterministic virtual clock)
5. Disabling jitter globally for exact delay verification
6. Resetting all deterministic state between tests

Usage:
    Just import this conftest.py — pytest auto-discovers it.
    Each test runs with seed=42 by default.

    Override per-test:
        import os
        os.environ["ZENIC_DETERMINISTIC_SEED"] = "12345"
"""

import os
import random

import pytest

# Fixed seed for all tests — ensures identical results across runs
_TEST_SEED = 42


@pytest.fixture(autouse=True, scope="function")
def _deterministic_test_setup():
    """
    Auto-applied fixture that guarantees deterministic state for every test.

    Before each test:
      - Sets the global deterministic seed
      - Installs uuid.uuid4() patch (all 95+ files become deterministic)
      - Installs random.* patch (all bare random calls become deterministic)
      - Installs time.time() patch (deterministic virtual clock)
      - Disables jitter for exact delay calculations
      - Resets all deterministic counters

    After each test:
      - Uninstalls time.time() patch (restores real wall clock)
      - Uninstalls uuid.uuid4() patch (restores real randomness)
      - Uninstalls random.* patch
      - Re-enables jitter (for production code)
      - Resets all deterministic state (clean slate for next test)
    """
    from src.core.shared.deterministic import (
        set_global_seed,
        reset_all_deterministic_state,
        ControllableJitter,
        install_uuid4_patch,
        uninstall_uuid4_patch,
        install_random_patch,
        uninstall_random_patch,
        install_time_patch,
        uninstall_time_patch,
    )

    # 1. Set deterministic seed (this also seeds Python's global random)
    set_global_seed(_TEST_SEED)

    # 2. Install uuid.uuid4() patch — covers ALL 95+ files automatically
    install_uuid4_patch()

    # 3. Install random.* patch — covers all bare random calls
    install_random_patch()

    # 4. Install time.time() patch — deterministic virtual clock
    install_time_patch(increment=0.001)

    # 5. Disable jitter for exact delay verification
    ControllableJitter.set_global_enabled(False)

    # Run the test
    yield

    # Cleanup: restore original behavior
    uninstall_time_patch()
    uninstall_uuid4_patch()
    uninstall_random_patch()
    ControllableJitter.set_global_enabled(True)
    reset_all_deterministic_state()


@pytest.fixture(scope="session")
def deterministic_seed():
    """Provide the test seed value for tests that need it explicitly."""
    return _TEST_SEED


@pytest.fixture(scope="function")
def seeded_rng():
    """
    Provide a fresh DeterministicRNG for tests that need direct RNG access.

    Usage::

        def test_mcts(seeded_rng):
            action = seeded_rng.choice(["A", "B", "C"])
            assert action == "B"  # Always B with seed=42
    """
    from src.core.shared.deterministic import DeterministicRNG
    return DeterministicRNG("test", seed_override=_TEST_SEED)


@pytest.fixture(scope="function")
def deterministic_uuid():
    """
    Provide a fresh DeterministicUUID for tests.

    Usage::

        def test_plan(deterministic_uuid):
            plan_id = deterministic_uuid.next()
            assert plan_id == "expected-uuid-string"
    """
    from src.core.shared.deterministic import DeterministicUUID
    return DeterministicUUID("test", seed_override=_TEST_SEED)


@pytest.fixture(scope="function")
def fencing_token_gen():
    """
    Provide a fresh FencingTokenGenerator for tests.

    Usage::

        def test_election(fencing_token_gen):
            token1 = fencing_token_gen.next()
            token2 = fencing_token_gen.next()
            assert token2 > token1
    """
    from src.core.shared.deterministic import FencingTokenGenerator
    return FencingTokenGenerator("test", seed_override=_TEST_SEED)


@pytest.fixture(scope="function")
def deterministic_clock():
    """
    Provide a fresh DeterministicClock for tests.

    Usage::

        def test_session(deterministic_clock):
            ts1 = deterministic_clock.time()
            ts2 = deterministic_clock.time()
            assert ts2 > ts1
    """
    from src.core.shared.deterministic import DeterministicClock
    return DeterministicClock("test", increment=0.1, seed_override=_TEST_SEED)
