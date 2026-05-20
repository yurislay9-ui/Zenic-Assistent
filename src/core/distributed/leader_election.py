"""
ZENIC-AGENTS - Leader Election

PostgreSQL-backed leader election using atomic INSERT/UPDATE with TTL.
Ensures exactly one leader per election name across all nodes.

Features:
    - TTL-based leadership with automatic expiry
    - Leadership renewal via background thread
    - Voluntary abdication (graceful step-down)
    - Leadership change detection for leader-only work
    - Fencing tokens for safe resource access
    - Works with PostgreSQL and MemoryBackend

Use Cases:
    - Lease expiration (task queue coordinator)
    - Single-writer for shared resources
    - Periodic job scheduling (only leader runs)
    - Cluster-wide configuration changes
"""

import enum
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .backend import CoordinationBackend
from src.core.shared.deterministic import FencingTokenGenerator

logger = logging.getLogger(__name__)

__all__ = [
    "LeaderElection",
    "LeadershipState",
]


# ============================================================
#  ENUMS
# ============================================================

class LeadershipState(str, enum.Enum):
    """Leadership states."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


# ============================================================
#  LEADER ELECTION
# ============================================================

class LeaderElection:
    """
    Distributed leader election with TTL-based leases.

    Uses the CoordinationBackend for persistent leadership state.
    Leadership has a TTL; the leader must periodically renew to
    maintain its position. If the leader crashes or fails to renew,
    another candidate can claim leadership.

    Usage::

        election = LeaderElection(
            election_name="task_coordinator",
            candidate_id="node-abc123",
            backend=backend,
            ttl_seconds=30.0,
        )

        # Campaign for leadership
        if await election.campaign():
            print("I am the leader!")
            # Start leader-only work...

        # Renew leadership periodically
        await election.renew()

        # Step down gracefully
        await election.abdicate()

    Background Renewal:
        Start the renewal thread to automatically maintain leadership::

        election.start_renewal()  # Background thread renews TTL
        election.stop_renewal()   # Stop renewal thread
    """

    def __init__(
        self,
        election_name: str,
        candidate_id: str,
        backend: CoordinationBackend,
        ttl_seconds: float = 30.0,
        renewal_interval: Optional[float] = None,
    ) -> None:
        """
        Initialize the leader election.

        Args:
            election_name: Name of the leadership position.
            candidate_id: ID of this candidate (usually node_id).
            backend: Coordination backend for persistent state.
            ttl_seconds: Leadership duration before re-campaign needed.
            renewal_interval: How often to renew (default: ttl/3).
        """
        if not election_name:
            raise ValueError("election_name must not be empty")

        self._election_name = election_name
        self._candidate_id = candidate_id
        self._backend = backend
        self._ttl_seconds = ttl_seconds
        self._renewal_interval = renewal_interval or (ttl_seconds / 3.0)

        self._state: LeadershipState = LeadershipState.FOLLOWER
        self._fencing_token: int = 0
        self._lock = threading.Lock()
        # Deterministic fencing token generator (Phase 5 fix)
        self._fencing_gen = FencingTokenGenerator(f"leader:{election_name}")

        # Background renewal
        self._renewal_thread: Optional[threading.Thread] = None
        self._stop_renewal_event = threading.Event()

        # Callbacks
        self._on_elected: Optional[Callable[[], None]] = None
        self._on_deposed: Optional[Callable[[], None]] = None

    # ----------------------------------------------------------
    #  PROPERTIES
    # ----------------------------------------------------------

    @property
    def election_name(self) -> str:
        """Name of the leadership position."""
        return self._election_name

    @property
    def candidate_id(self) -> str:
        """This candidate's ID."""
        return self._candidate_id

    @property
    def state(self) -> LeadershipState:
        """Current leadership state."""
        return self._state

    @property
    def is_leader(self) -> bool:
        """Whether this candidate is currently the leader."""
        return self._state == LeadershipState.LEADER

    @property
    def fencing_token(self) -> int:
        """
        Monotonically increasing fencing token.

        Useful for ensuring resource access is only granted to
        the current leader. If leadership changes, the new leader
        gets a higher fencing token.
        """
        return self._fencing_token

    # ----------------------------------------------------------
    #  CAMPAIGN
    # ----------------------------------------------------------

    async def campaign(self) -> bool:
        """
        Attempt to become leader.

        Returns:
            True if this candidate is now the leader.
        """
        success = await self._backend.campaign(
            self._election_name,
            self._candidate_id,
            self._ttl_seconds,
        )

        if success:
            with self._lock:
                was_not_leader = self._state != LeadershipState.LEADER
                self._state = LeadershipState.LEADER
                self._fencing_token = self._fencing_gen.next()

            logger.info(
                "LeaderElection: '%s' — %s is now LEADER "
                "(fencing_token=%d)",
                self._election_name, self._candidate_id,
                self._fencing_token,
            )

            if was_not_leader and self._on_elected:
                try:
                    self._on_elected()
                except Exception as exc:
                    logger.error(
                        "LeaderElection: on_elected callback error: %s", exc,
                    )
        else:
            with self._lock:
                self._state = LeadershipState.FOLLOWER

        return success

    # ----------------------------------------------------------
    #  ABDICATE
    # ----------------------------------------------------------

    async def abdicate(self) -> bool:
        """
        Voluntarily step down as leader.

        Returns:
            True if leadership was relinquished.
        """
        success = await self._backend.abdicate(
            self._election_name,
            self._candidate_id,
        )

        if success:
            with self._lock:
                self._state = LeadershipState.FOLLOWER

            logger.info(
                "LeaderElection: '%s' — %s abdicated",
                self._election_name, self._candidate_id,
            )

            if self._on_deposed:
                try:
                    self._on_deposed()
                except Exception as exc:
                    logger.error(
                        "LeaderElection: on_deposed callback error: %s", exc,
                    )

        return success

    # ----------------------------------------------------------
    #  RENEW
    # ----------------------------------------------------------

    async def renew(self) -> bool:
        """
        Renew leadership before it expires.

        Returns:
            True if leadership was renewed.
        """
        if self._state != LeadershipState.LEADER:
            return False

        success = await self._backend.renew_leadership(
            self._election_name,
            self._candidate_id,
            self._ttl_seconds,
        )

        if not success:
            # Lost leadership
            with self._lock:
                self._state = LeadershipState.FOLLOWER

            logger.warning(
                "LeaderElection: '%s' — %s lost leadership (renew failed)",
                self._election_name, self._candidate_id,
            )

            if self._on_deposed:
                try:
                    self._on_deposed()
                except Exception as exc:
                    logger.error(
                        "LeaderElection: on_deposed callback error: %s", exc,
                    )

        return success

    # ----------------------------------------------------------
    #  QUERY
    # ----------------------------------------------------------

    async def get_leader(self) -> Optional[str]:
        """
        Get the current leader for this election.

        Returns:
            Leader ID, or None if no leader.
        """
        return await self._backend.get_leader(self._election_name)

    # ----------------------------------------------------------
    #  BACKGROUND RENEWAL
    # ----------------------------------------------------------

    def start_renewal(self) -> None:
        """
        Start a background thread that automatically renews leadership.

        Should be called after successfully campaigning.
        """
        if self._renewal_thread and self._renewal_thread.is_alive():
            return

        self._stop_renewal_event.clear()
        self._renewal_thread = threading.Thread(
            target=self._renewal_loop,
            name=f"leader-renewal-{self._election_name}",
            daemon=True,
        )
        self._renewal_thread.start()
        logger.debug(
            "LeaderElection: Started renewal for '%s' "
            "(interval=%.1fs)",
            self._election_name, self._renewal_interval,
        )

    def stop_renewal(self) -> None:
        """Stop the background renewal thread."""
        self._stop_renewal_event.set()
        if self._renewal_thread and self._renewal_thread.is_alive():
            self._renewal_thread.join(timeout=5.0)
        logger.debug(
            "LeaderElection: Stopped renewal for '%s'",
            self._election_name,
        )

    def _renewal_loop(self) -> None:
        """Background loop that renews leadership."""
        while not self._stop_renewal_event.is_set():
            if self._state == LeadershipState.LEADER:
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(self.renew())
                    finally:
                        loop.close()
                except Exception as exc:
                    logger.error(
                        "LeaderElection: Renewal error for '%s': %s",
                        self._election_name, exc,
                    )

            self._stop_renewal_event.wait(
                timeout=self._renewal_interval
            )

    # ----------------------------------------------------------
    #  CALLBACKS
    # ----------------------------------------------------------

    def on_elected(self, callback: Callable[[], None]) -> None:
        """
        Register a callback for when this candidate becomes leader.

        Args:
            callback: Called when leadership is acquired.
        """
        self._on_elected = callback

    def on_deposed(self, callback: Callable[[], None]) -> None:
        """
        Register a callback for when this candidate loses leadership.

        Args:
            callback: Called when leadership is lost.
        """
        self._on_deposed = callback

    # ----------------------------------------------------------
    #  STATS
    # ----------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """Election statistics."""
        return {
            "election_name": self._election_name,
            "candidate_id": self._candidate_id,
            "state": self._state.value,
            "is_leader": self.is_leader,
            "fencing_token": self._fencing_token,
            "ttl_seconds": self._ttl_seconds,
            "renewal_interval": self._renewal_interval,
        }
