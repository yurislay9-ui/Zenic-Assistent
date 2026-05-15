"""
Unit tests for Rate Limiter

NOTE: src.server.rate_limiter has been removed (server module deleted).
These tests are disabled. The RateLimiter was part of the HTTP server
which is no longer available.
"""

import pytest

# Server module removed — RateLimiter no longer available
# from src.server.rate_limiter import RateLimiter

pytestmark = pytest.mark.skip(reason="src.server.rate_limiter removed — server module deleted")


class TestRateLimiter:
    """Tests for the RateLimiter class — DISABLED (server removed)."""

    def test_acquire_allows_request(self):
        """Should allow requests within limits."""
        pass

    def test_acquire_tracks_active_requests(self):
        """Should track active request count."""
        pass

    def test_release_decrements_active(self):
        """Release should decrement active request count."""
        pass

    def test_burst_size_limit(self):
        """Should reject requests after burst is exhausted."""
        pass

    def test_global_concurrent_limit(self):
        """Should reject when global concurrent limit is reached."""
        pass

    def test_separate_ip_buckets(self):
        """Different IPs should have separate token buckets."""
        pass

    def test_token_refill(self):
        """Tokens should refill over time."""
        pass

    def test_get_stats(self):
        """Stats should reflect current state."""
        pass

    def test_rejected_increments_counter(self):
        """Rejected requests should increment rejected counter."""
        pass

    def test_release_never_goes_negative(self):
        """Active requests should never go below 0."""
        pass
