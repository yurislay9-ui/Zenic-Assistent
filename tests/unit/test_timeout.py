"""
Unit tests for Timeout Enforcer

Tests timeout enforcement, successful execution, and exception handling.
"""

import pytest
import time
from src.core.shared.timeout import TimeoutEnforcer


class TestTimeoutEnforcer:
    """Tests for the TimeoutEnforcer class."""

    def test_fast_function_completes(self):
        """Fast functions should complete within timeout."""
        enforcer = TimeoutEnforcer(timeout_ms=5000)
        result, timed_out = enforcer.execute_with_timeout(lambda: 42)
        assert result == 42
        assert timed_out is False

    def test_slow_function_times_out(self):
        """Slow functions should trigger timeout."""
        enforcer = TimeoutEnforcer(timeout_ms=100)
        result, timed_out = enforcer.execute_with_timeout(
            lambda: time.sleep(0.5)
        )
        assert timed_out is True

    def test_function_with_args(self):
        """Should pass arguments correctly to the function."""
        enforcer = TimeoutEnforcer(timeout_ms=5000)
        result, timed_out = enforcer.execute_with_timeout(
            lambda x, y: x + y, 3, 4
        )
        assert result == 7
        assert timed_out is False

    def test_function_with_kwargs(self):
        """Should pass keyword arguments correctly."""
        enforcer = TimeoutEnforcer(timeout_ms=5000)

        def greet(name="World"):
            return f"Hello, {name}!"

        result, timed_out = enforcer.execute_with_timeout(greet, name="ZENIC")
        assert result == "Hello, ZENIC!"
        assert timed_out is False

    def test_exception_propagation(self):
        """Exceptions from the function should be propagated."""
        enforcer = TimeoutEnforcer(timeout_ms=5000)

        def raise_error():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            enforcer.execute_with_timeout(raise_error)

    def test_timed_out_property(self):
        """timed_out property should reflect last execution state."""
        enforcer = TimeoutEnforcer(timeout_ms=100)
        enforcer.execute_with_timeout(lambda: time.sleep(0.5))
        assert enforcer.timed_out is True

    def test_timed_out_resets_on_new_execution(self):
        """timed_out should reset between executions."""
        enforcer = TimeoutEnforcer(timeout_ms=100)
        enforcer.execute_with_timeout(lambda: time.sleep(0.5))
        assert enforcer.timed_out is True

        enforcer.execute_with_timeout(lambda: 1)
        assert enforcer.timed_out is False

    def test_zero_timeout(self):
        """Zero timeout should immediately timeout."""
        enforcer = TimeoutEnforcer(timeout_ms=0)
        # Very fast function might still complete with 0 timeout
        # due to thread scheduling, so we test with a slow function
        result, timed_out = enforcer.execute_with_timeout(
            lambda: time.sleep(1)
        )
        assert timed_out is True

    def test_returns_none_on_timeout(self):
        """Should return None as result when timeout occurs."""
        enforcer = TimeoutEnforcer(timeout_ms=50)
        result, timed_out = enforcer.execute_with_timeout(
            lambda: time.sleep(1.0)
        )
        assert result is None
        assert timed_out is True
