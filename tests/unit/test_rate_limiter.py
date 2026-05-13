"""
Unit tests for Rate Limiter

Tests token bucket algorithm, global concurrent limit, and cleanup.
"""

import pytest
from src.server.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_acquire_allows_request(self):
        """Should allow requests within limits."""
        limiter = RateLimiter(max_requests_per_minute=30, burst_size=10)
        assert limiter.acquire("127.0.0.1") is True

    def test_acquire_tracks_active_requests(self):
        """Should track active request count."""
        limiter = RateLimiter(max_requests_per_minute=30, burst_size=10)
        limiter.acquire("127.0.0.1")
        stats = limiter.get_stats()
        assert stats["active_requests"] == 1

    def test_release_decrements_active(self):
        """Release should decrement active request count."""
        limiter = RateLimiter(max_requests_per_minute=30, burst_size=10)
        limiter.acquire("127.0.0.1")
        limiter.release()
        stats = limiter.get_stats()
        assert stats["active_requests"] == 0

    def test_burst_size_limit(self):
        """Should reject requests after burst is exhausted."""
        limiter = RateLimiter(max_requests_per_minute=1, burst_size=3)
        # First 3 should succeed (burst)
        for _ in range(3):
            assert limiter.acquire("127.0.0.1") is True
            limiter.release()
        # 4th should be rejected (no tokens, slow refill)
        assert limiter.acquire("127.0.0.1") is False

    def test_global_concurrent_limit(self):
        """Should reject when global concurrent limit is reached."""
        limiter = RateLimiter(
            max_requests_per_minute=1000,
            burst_size=100,
            global_max_concurrent=2,
        )
        # Acquire 2 slots
        limiter.acquire("192.168.1.1")
        limiter.acquire("192.168.1.2")
        # 3rd should fail (global limit)
        assert limiter.acquire("192.168.1.3") is False

    def test_separate_ip_buckets(self):
        """Different IPs should have separate token buckets."""
        limiter = RateLimiter(max_requests_per_minute=1, burst_size=1)
        assert limiter.acquire("192.168.1.1") is True
        limiter.release()
        # Same IP should be limited
        assert limiter.acquire("192.168.1.1") is False
        # Different IP should be allowed
        assert limiter.acquire("192.168.1.2") is True

    def test_token_refill(self):
        """Tokens should refill over time."""
        from unittest.mock import patch

        _time_counter = [0.0]

        def fake_time():
            return _time_counter[0]

        with patch('src.server.rate_limiter.time.time', side_effect=fake_time):
            limiter = RateLimiter(max_requests_per_minute=60, burst_size=1)
            limiter.acquire("127.0.0.1")
            limiter.release()
            # Exhausted, no tokens remain
            assert limiter.acquire("127.0.0.1") is False
            # Advance time by 1 second — token should refill
            _time_counter[0] = 1.0
            assert limiter.acquire("127.0.0.1") is True

    def test_get_stats(self):
        """Stats should reflect current state."""
        limiter = RateLimiter(
            max_requests_per_minute=30,
            burst_size=10,
            global_max_concurrent=20,
        )
        limiter.acquire("127.0.0.1")
        stats = limiter.get_stats()
        assert stats["active_clients"] == 1
        assert stats["active_requests"] == 1
        assert stats["total_accepted"] == 1
        assert stats["total_rejected"] == 0

    def test_rejected_increments_counter(self):
        """Rejected requests should increment rejected counter."""
        limiter = RateLimiter(max_requests_per_minute=1, burst_size=1)
        limiter.acquire("127.0.0.1")
        limiter.release()
        limiter.acquire("127.0.0.1")  # Should be rejected
        stats = limiter.get_stats()
        assert stats["total_rejected"] == 1

    def test_release_never_goes_negative(self):
        """Active requests should never go below 0."""
        limiter = RateLimiter()
        limiter.release()  # Release without acquire
        assert limiter.get_stats()["active_requests"] == 0
