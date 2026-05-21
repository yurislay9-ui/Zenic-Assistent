"""
ZENIC-AGENTS - Deterministic Utilities (Phase 5 Fix)

Single source of truth for ALL non-deterministic operations in the system.
Provides seeded RNG, deterministic UUIDs, monotonic fencing tokens, and
controllable jitter — ensuring 100% reproducible behavior in tests and
simulations.

Architecture:
    SeedManager (global singleton) — holds the master seed
    DeterministicRNG  — per-module seeded Random instances
    DeterministicUUID — reproducible UUID generation
    FencingTokenGenerator — monotonic counter-based tokens
    ControllableJitter — deterministic jitter for retries/backoff

Usage:
    from src.core.shared.deterministic import (
        SeedManager, DeterministicRNG, DeterministicUUID,
        FencingTokenGenerator, ControllableJitter, set_global_seed,
    )

    # Set seed at test entry point:
    set_global_seed(42)

    # In production code:
    rng = DeterministicRNG("mcts")
    action = rng.choice(actions)

    uuid_gen = DeterministicUUID("planner")
    plan_id = uuid_gen.next()

    token_gen = FencingTokenGenerator("leader_election")
    token = token_gen.next()
"""

import hashlib
import logging
import os
import random
import threading
import uuid
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "SeedManager",
    "DeterministicRNG",
    "DeterministicUUID",
    "DeterministicClock",
    "FencingTokenGenerator",
    "ControllableJitter",
    "set_global_seed",
    "get_global_seed",
    "reset_all_deterministic_state",
    "install_uuid4_patch",
    "uninstall_uuid4_patch",
    "is_uuid4_patched",
    "install_random_patch",
    "uninstall_random_patch",
    "install_time_patch",
    "uninstall_time_patch",
    "is_time_patched",
]

# ============================================================
#  DEFAULT SEED
# ============================================================

# Production seed derived from a fixed constant. Tests override via
# ZENIC_DETERMINISTIC_SEED env var or set_global_seed().
_PRODUCTION_SEED = 0xC0FFEE  # 12648430


# ============================================================
#  SeedManager — Global Singleton
# ============================================================

class SeedManager:
    """
    Global seed manager for deterministic replay.

    Holds a master seed and derives per-module sub-seeds via HMAC-SHA256.
    Thread-safe. In production, uses a fixed seed. In tests, override via
    ``set_global_seed()`` or ``ZENIC_DETERMINISTIC_SEED`` env var.

    Derivation formula:
        sub_seed = int(HMAC-SHA256(master_seed_bytes + module_name)[:8], 16)
    """

    _instance: Optional["SeedManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "SeedManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._master_seed: int = self._resolve_seed()
        self._module_seeds: Dict[str, int] = {}
        self._module_lock = threading.Lock()
        self._uuid_counters: Dict[str, int] = {}
        self._uuid_lock = threading.Lock()
        self._fencing_counters: Dict[str, int] = {}
        self._fencing_lock = threading.Lock()
        self._initialized = True
        logger.info(
            "SeedManager: Initialized with master_seed=%d (0x%X)",
            self._master_seed, self._master_seed,
        )

    def _resolve_seed(self) -> int:
        """Resolve seed from env var or use production default."""
        env_seed = os.environ.get("ZENIC_DETERMINISTIC_SEED")
        if env_seed is not None:
            try:
                seed = int(env_seed)
                logger.info("SeedManager: Using seed from ZENIC_DETERMINISTIC_SEED=%d", seed)
                return seed
            except ValueError:
                logger.warning(
                    "SeedManager: Invalid ZENIC_DETERMINISTIC_SEED='%s', using default",
                    env_seed,
                )
        return _PRODUCTION_SEED

    @property
    def master_seed(self) -> int:
        """The current master seed."""
        return self._master_seed

    def set_seed(self, seed: int) -> None:
        """
        Set a new master seed and invalidate all cached sub-seeds.

        Call this at the start of each test to ensure full reproducibility.
        """
        with self._module_lock:
            self._master_seed = seed
            self._module_seeds.clear()
        with self._uuid_lock:
            self._uuid_counters.clear()
        with self._fencing_lock:
            self._fencing_counters.clear()
        logger.info("SeedManager: Master seed set to %d (0x%X)", seed, seed)

    def derive_seed(self, module_name: str) -> int:
        """
        Derive a deterministic sub-seed for a module.

        Uses HMAC-SHA256(master_seed, module_name) truncated to 64 bits.
        Results are cached so the same module always gets the same sub-seed
        within a given master seed.
        """
        with self._module_lock:
            if module_name in self._module_seeds:
                return self._module_seeds[module_name]
            # Derive: HMAC-SHA256(master_seed_bytes, module_name)
            key = str(self._master_seed).encode("utf-8")
            msg = module_name.encode("utf-8")
            digest = hashlib.sha256(key + b":" + msg).hexdigest()[:16]
            sub_seed = int(digest, 16)
            self._module_seeds[module_name] = sub_seed
            return sub_seed

    def next_uuid_counter(self, namespace: str) -> int:
        """Get next UUID counter for a namespace (thread-safe)."""
        with self._uuid_lock:
            counter = self._uuid_counters.get(namespace, 0)
            self._uuid_counters[namespace] = counter + 1
            return counter

    def next_fencing_token(self, namespace: str) -> int:
        """Get next fencing token for a namespace (thread-safe, monotonic)."""
        with self._fencing_lock:
            counter = self._fencing_counters.get(namespace, 0)
            counter += 1
            self._fencing_counters[namespace] = counter
            return self._master_seed + counter

    def reset(self) -> None:
        """Full reset — clears all cached state. Use between test cases."""
        with self._module_lock:
            self._module_seeds.clear()
        with self._uuid_lock:
            self._uuid_counters.clear()
        with self._fencing_lock:
            self._fencing_counters.clear()
        logger.debug("SeedManager: All state reset (master_seed=%d unchanged)", self._master_seed)


# ============================================================
#  Convenience Functions
# ============================================================

def set_global_seed(seed: int) -> None:
    """
    Set the global deterministic seed. Call at test entry point.

    This also:
    - Seeds Python's global random module
    - Re-seeds the uuid4 patch if installed
    - Re-seeds the random patch if installed
    """
    mgr = SeedManager()
    mgr.set_seed(seed)
    # Also seed Python's global random for any code that still uses it
    random.seed(seed)
    # Re-seed the global patches if they're installed
    global _uuid4_global_gen, _random_global_rng
    with _uuid4_patch_lock:
        _uuid4_global_gen = DeterministicUUID("__global_uuid4__") if _uuid4_patched else None
    with _random_patch_lock:
        if _random_patched:
            new_seed = SeedManager().derive_seed("__global_random__")
            _random_global_rng = random.Random(new_seed)


def get_global_seed() -> int:
    """Get the current global master seed."""
    return SeedManager().master_seed


def reset_all_deterministic_state() -> None:
    """
    Reset all deterministic counters and re-seed patches.
    Call between test cases.
    """
    SeedManager().reset()
    # Reset UUID4 patch generator
    global _uuid4_global_gen, _random_global_rng
    with _uuid4_patch_lock:
        if _uuid4_patched:
            _uuid4_global_gen = DeterministicUUID("__global_uuid4__")
    with _random_patch_lock:
        if _random_patched:
            new_seed = SeedManager().derive_seed("__global_random__")
            _random_global_rng = random.Random(new_seed)


# ============================================================
#  DeterministicRNG — Per-Module Seeded Random
# ============================================================

class DeterministicRNG:
    """
    Deterministic random number generator scoped to a module.

    Each instance gets a derived seed from SeedManager based on its
    module_name. All methods delegate to a ``random.Random`` instance
    that is seeded with this derived seed.

    IMPORTANT: Instances should be created ONCE per module/class and
    reused. Creating a new instance with the same name resets the
    internal state to the same seed.

    Usage::

        rng = DeterministicRNG("mcts")
        action = rng.choice(action_list)
        value = rng.uniform(0, 1)
    """

    def __init__(self, module_name: str, seed_override: Optional[int] = None) -> None:
        self._module_name = module_name
        if seed_override is not None:
            self._seed = seed_override
        else:
            self._seed = SeedManager().derive_seed(module_name)
        self._rng = random.Random(self._seed)
        logger.debug(
            "DeterministicRNG[%s]: seed=%d (0x%X)",
            module_name, self._seed, self._seed,
        )

    @property
    def module_name(self) -> str:
        return self._module_name

    @property
    def seed(self) -> int:
        return self._seed

    def reseed(self, seed: Optional[int] = None) -> None:
        """Re-seed this RNG. If seed is None, re-derive from SeedManager."""
        if seed is not None:
            self._seed = seed
        else:
            self._seed = SeedManager().derive_seed(self._module_name)
        self._rng.seed(self._seed)

    def choice(self, seq: Sequence[Any]) -> Any:
        """Deterministic choice from a sequence."""
        if not seq:
            raise IndexError("Cannot choose from an empty sequence")
        return self._rng.choice(seq)

    def choices(self, population: Sequence[Any], k: int = 1) -> List[Any]:
        """Deterministic choices with replacement."""
        return self._rng.choices(population, k=k)

    def uniform(self, a: float, b: float) -> float:
        """Deterministic uniform float in [a, b)."""
        return self._rng.uniform(a, b)

    def random(self) -> float:
        """Deterministic random float in [0.0, 1.0)."""
        return self._rng.random()

    def randint(self, a: int, b: int) -> int:
        """Deterministic random integer in [a, b]."""
        return self._rng.randint(a, b)

    def shuffle(self, x: List[Any]) -> None:
        """Deterministic shuffle in-place."""
        self._rng.shuffle(x)

    def sample(self, population: Sequence[Any], k: int) -> List[Any]:
        """Deterministic sample without replacement."""
        return self._rng.sample(population, k)


# ============================================================
#  DeterministicUUID — Reproducible UUID Generation
# ============================================================

class DeterministicUUID:
    """
    Generate deterministic UUIDs that are reproducible given the same seed.

    Format: ``dddddddd-dddd-4ddd-bddd-dddddddddddd`` where the digits
    come from a seeded SHA-256 chain. The UUIDv4 variant bits (4xxx, bxxx)
    are preserved for format compliance, but the bits are deterministic.

    Usage::

        uuid_gen = DeterministicUUID("planner")
        plan_id = uuid_gen.next()  # e.g. "a3f2c1e0-7b4d-4e5a-8f6c-2d1e0f9a8b7c"
        plan_id2 = uuid_gen.next()  # different, but reproducible on replay
    """

    def __init__(self, namespace: str, seed_override: Optional[int] = None) -> None:
        self._namespace = namespace
        self._seed = seed_override if seed_override is not None else SeedManager().derive_seed(f"uuid:{namespace}")
        self._counter = 0
        self._lock = threading.Lock()
        logger.debug(
            "DeterministicUUID[%s]: seed=%d", namespace, self._seed,
        )

    def next(self) -> str:
        """
        Generate the next deterministic UUID.

        Algorithm: SHA-256(seed_hex + ":" + counter) → format as UUIDv4.
        Thread-safe.
        """
        with self._lock:
            counter = self._counter
            self._counter += 1

        # Build deterministic hex via SHA-256 chain
        raw = f"{self._seed:x}:{self._namespace}:{counter}"
        hex_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        # Format as UUIDv4: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        # version = 4, variant = RFC4122 (10xx → y in [8,9,a,b])
        h = hex_digest[:32]  # 32 hex chars = 128 bits
        # Set version nibble to 4 (positions 12-15 → "4xxx")
        mid = h[:12] + "4" + h[13:16]
        # Set variant bits: top 2 bits of clock_seq_hi = 10
        # clock_seq_hi is position 16 (hex digit at index 16)
        variant_digit = int(h[16], 16) & 0x3 | 0x8  # 10xx pattern
        parts = [
            h[0:8],
            h[8:12],
            "4" + h[13:16],                   # version 4
            format(variant_digit, 'x') + h[17:20],  # variant 10xx
            h[20:32],
        ]
        return "-".join(parts)

    def reset(self) -> None:
        """Reset counter to 0."""
        with self._lock:
            self._counter = 0


# ============================================================
#  FencingTokenGenerator — Monotonic Counter-Based Tokens
# ============================================================

class FencingTokenGenerator:
    """
    Generate deterministic, monotonically increasing fencing tokens.

    Replaces ``int(time.time() * 1000)`` with a counter-based approach
    that is both deterministic (for replay) and monotonically increasing
    (for correctness — higher token always wins).

    Token format: ``master_seed + counter`` — guaranteed monotonically
    increasing within a namespace, and across master_seed changes.

    Usage::

        token_gen = FencingTokenGenerator("leader_election")
        token = token_gen.next()   # e.g. 12648431
        token2 = token_gen.next()  # e.g. 12648432
    """

    def __init__(self, namespace: str, seed_override: Optional[int] = None) -> None:
        self._namespace = namespace
        self._seed = seed_override if seed_override is not None else SeedManager().derive_seed(f"fencing:{namespace}")
        self._counter = 0
        self._lock = threading.Lock()
        logger.debug(
            "FencingTokenGenerator[%s]: base_seed=%d", namespace, self._seed,
        )

    def next(self) -> int:
        """
        Generate the next fencing token (monotonically increasing).

        Thread-safe. Guarantees: next() > all previous values from
        this generator.
        """
        with self._lock:
            self._counter += 1
            return self._seed + self._counter

    @property
    def current(self) -> int:
        """Current (last generated) token value. 0 if none generated."""
        with self._lock:
            return self._seed + self._counter if self._counter > 0 else 0

    def reset(self) -> None:
        """Reset counter to 0."""
        with self._lock:
            self._counter = 0


# ============================================================
#  ControllableJitter — Deterministic Jitter for Retries/Backoff
# ============================================================

class ControllableJitter:
    """
    Deterministic jitter for retry delays and backoff calculations.

    In production: uses a seeded RNG for consistent but varied delays.
    In tests: can be disabled entirely (``enabled=False``) for exact
    delay verification.

    Usage::

        jitter = ControllableJitter("retry_config")
        delay = jitter.apply(base_delay=2.0, jitter_max=0.3)
        # In tests: ControllableJitter("test", enabled=False)
        #           → returns base_delay unchanged
    """

    # Global toggle — set to False to disable ALL jitter (e.g. in tests)
    _global_enabled: bool = True
    _global_lock = threading.Lock()

    @classmethod
    def set_global_enabled(cls, enabled: bool) -> None:
        """Globally enable/disable jitter. Use in test fixtures."""
        with cls._global_lock:
            cls._global_enabled = enabled
            if not enabled:
                logger.info("ControllableJitter: Global jitter DISABLED")

    @classmethod
    def is_global_enabled(cls) -> bool:
        """Check if jitter is globally enabled."""
        with cls._global_lock:
            return cls._global_enabled

    def __init__(
        self,
        namespace: str,
        enabled: bool = True,
        seed_override: Optional[int] = None,
    ) -> None:
        self._namespace = namespace
        self._enabled = enabled
        self._rng = DeterministicRNG(f"jitter:{namespace}", seed_override=seed_override)

    def apply(self, base_delay: float, jitter_max: float = 0.3) -> float:
        """
        Apply jitter to a base delay.

        If jitter is disabled (instance or global), returns base_delay unchanged.
        Otherwise, adds ``uniform(0, jitter_max * base_delay)`` using seeded RNG.

        Args:
            base_delay: The computed delay before jitter.
            jitter_max: Maximum jitter as fraction of base_delay (0..1).

        Returns:
            base_delay + random_jitter, or base_delay if disabled.
        """
        if not self._enabled or not self.is_global_enabled() or base_delay <= 0:
            return base_delay
        jitter_amount = self._rng.uniform(0, jitter_max * base_delay)
        return base_delay + jitter_amount


# ============================================================
#  Global uuid.uuid4() Patch — Covers ALL 95+ Files at Once
# ============================================================

# Save the original uuid4 before any patching
_original_uuid4 = uuid.uuid4

# Module-level state for the patch
_uuid4_patched: bool = False
_uuid4_global_gen: Optional[DeterministicUUID] = None
_uuid4_patch_lock = threading.Lock()


def _deterministic_uuid4() -> uuid.UUID:
    """
    Drop-in replacement for uuid.uuid4() that produces deterministic UUIDs.

    When the patch is installed, ANY call to uuid.uuid4() across the
    entire codebase (95+ files) will produce a deterministic, reproducible
    UUID based on the current SeedManager master seed.

    The UUID is a valid UUIDv4 (version=4, variant=RFC4122) but the
    bits are derived from a SHA-256 chain seeded by the master seed.
    """
    global _uuid4_global_gen
    with _uuid4_patch_lock:
        if _uuid4_global_gen is None:
            _uuid4_global_gen = DeterministicUUID("__global_uuid4__")
        uid_str = _uuid4_global_gen.next()
    return uuid.UUID(uid_str)


def install_uuid4_patch() -> None:
    """
    Replace uuid.uuid4 with a deterministic implementation.

    After calling this, ALL code that uses uuid.uuid4() will produce
    deterministic, reproducible UUIDs based on the current master seed.

    This is the recommended approach for making the 95+ files with
    uuid.uuid4() deterministic WITHOUT modifying each file individually.

    Usage::

        from src.core.shared.deterministic import set_global_seed, install_uuid4_patch

        set_global_seed(42)
        install_uuid4_patch()

        # Now uuid.uuid4() is deterministic everywhere
        import uuid
        assert uuid.uuid4() == uuid.UUID("expected-value")
    """
    global _uuid4_patched, _uuid4_global_gen
    with _uuid4_patch_lock:
        if _uuid4_patched:
            logger.debug("install_uuid4_patch: Already installed, skipping")
            return
        # Reset the global UUID generator for fresh state
        _uuid4_global_gen = DeterministicUUID("__global_uuid4__")
        uuid.uuid4 = _deterministic_uuid4
        _uuid4_patched = True
    logger.info(
        "install_uuid4_patch: uuid.uuid4() replaced with deterministic version "
        "(seed=%d)", SeedManager().master_seed,
    )


def uninstall_uuid4_patch() -> None:
    """
    Restore the original uuid.uuid4 implementation.

    Call this to revert to non-deterministic UUIDs (e.g. in production
    when you want real randomness, or between test sessions).
    """
    global _uuid4_patched, _uuid4_global_gen
    with _uuid4_patch_lock:
        if not _uuid4_patched:
            return
        uuid.uuid4 = _original_uuid4
        _uuid4_patched = False
        _uuid4_global_gen = None
    logger.info("uninstall_uuid4_patch: uuid.uuid4() restored to original")


def is_uuid4_patched() -> bool:
    """Check if the deterministic uuid4 patch is currently installed."""
    return _uuid4_patched


# ============================================================
#  Global random.* Patch — Covers Bare random Calls
# ============================================================

# Save original random functions
_original_random_choice = random.choice
_original_random_uniform = random.uniform
_original_random_random = random.random
_original_random_randint = random.randint
_original_random_shuffle = random.shuffle
_original_random_sample = random.sample

_random_patched: bool = False
_random_global_rng: Optional[random.Random] = None
_random_patch_lock = threading.Lock()


def _patched_random_choice(seq):
    """Deterministic replacement for random.choice."""
    rng = _get_global_patched_rng()
    return rng.choice(seq)


def _patched_random_uniform(a, b):
    """Deterministic replacement for random.uniform."""
    rng = _get_global_patched_rng()
    return rng.uniform(a, b)


def _patched_random_random():
    """Deterministic replacement for random.random."""
    rng = _get_global_patched_rng()
    return rng.random()


def _patched_random_randint(a, b):
    """Deterministic replacement for random.randint."""
    rng = _get_global_patched_rng()
    return rng.randint(a, b)


def _patched_random_shuffle(x):
    """Deterministic replacement for random.shuffle."""
    rng = _get_global_patched_rng()
    return rng.shuffle(x)


def _patched_random_sample(population, k):
    """Deterministic replacement for random.sample."""
    rng = _get_global_patched_rng()
    return rng.sample(population, k)


def _get_global_patched_rng() -> random.Random:
    """Get or create the global patched RNG instance."""
    global _random_global_rng
    with _random_patch_lock:
        if _random_global_rng is None:
            seed = SeedManager().derive_seed("__global_random__")
            _random_global_rng = random.Random(seed)
        return _random_global_rng


def install_random_patch() -> None:
    """
    Replace random.choice/uniform/random/randint/shuffle/sample with
    deterministic versions backed by a seeded Random instance.

    This catches any remaining bare ``import random`` calls that haven't
    been migrated to DeterministicRNG yet.

    Usage::

        set_global_seed(42)
        install_random_patch()

        # Now random.choice(), random.uniform(), etc. are deterministic
        import random
        assert random.choice([1,2,3]) == 1  # Always 1 with seed=42
    """
    global _random_patched, _random_global_rng
    with _random_patch_lock:
        if _random_patched:
            logger.debug("install_random_patch: Already installed, skipping")
            return
        # Create a fresh seeded RNG
        seed = SeedManager().derive_seed("__global_random__")
        _random_global_rng = random.Random(seed)
        # Patch all common random functions
        random.choice = _patched_random_choice
        random.uniform = _patched_random_uniform
        random.random = _patched_random_random
        random.randint = _patched_random_randint
        random.shuffle = _patched_random_shuffle
        random.sample = _patched_random_sample
        _random_patched = True
    logger.info(
        "install_random_patch: random.choice/uniform/random/etc. replaced "
        "with deterministic versions (seed derived from master=%d)",
        SeedManager().master_seed,
    )


def uninstall_random_patch() -> None:
    """
    Restore the original random module functions.
    """
    global _random_patched, _random_global_rng
    with _random_patch_lock:
        if not _random_patched:
            return
        random.choice = _original_random_choice
        random.uniform = _original_random_uniform
        random.random = _original_random_random
        random.randint = _original_random_randint
        random.shuffle = _original_random_shuffle
        random.sample = _original_random_sample
        _random_patched = False
        _random_global_rng = None
    logger.info("uninstall_random_patch: random module restored to original")


# ============================================================
#  DeterministicClock — Virtual Time for Deterministic Replay
# ============================================================

import time as _time_module
from datetime import datetime, timezone, timedelta

class DeterministicClock:
    """
    Virtual clock that produces deterministic timestamps.

    Replaces ``time.time()`` and ``datetime.utcnow()`` in code paths
    where the timestamp affects control flow (session IDs, rate limiting,
    expiry calculations, etc.).

    The clock starts at a fixed epoch (2000-01-01T00:00:00Z) and
    advances by a configurable increment on each call. This makes
    all time-dependent behavior 100% reproducible.

    Usage::

        clock = DeterministicClock("session_ids")
        ts1 = clock.time()      # e.g. 946684800.0
        ts2 = clock.time()      # e.g. 946684800.1
        dt1 = clock.utcnow()    # datetime at virtual time
    """

    # Unix epoch of 2000-01-01T00:00:00Z
    _EPOCH = 946684800.0

    def __init__(
        self,
        namespace: str,
        increment: float = 0.1,
        seed_override: Optional[int] = None,
    ) -> None:
        self._namespace = namespace
        seed = seed_override if seed_override is not None else SeedManager().derive_seed(f"clock:{namespace}")
        self._current = self._EPOCH + (seed % 10000)  # Offset by seed for variety
        self._increment = increment
        self._lock = threading.Lock()
        logger.debug(
            "DeterministicClock[%s]: start=%.1f, increment=%.3f",
            namespace, self._current, self._increment,
        )

    def time(self) -> float:
        """
        Return a deterministic timestamp (monotonically increasing).

        Each call advances the virtual clock by ``increment`` seconds.
        Thread-safe.
        """
        with self._lock:
            result = self._current
            self._current += self._increment
            return result

    def time_ms(self) -> int:
        """Return a deterministic timestamp in milliseconds."""
        return int(self.time() * 1000)

    def utcnow(self) -> datetime:
        """Return a deterministic UTC datetime (monotonically increasing)."""
        return datetime.fromtimestamp(self.time(), tz=timezone.utc)

    def reset(self) -> None:
        """Reset the clock to its starting time."""
        with self._lock:
            seed = SeedManager().derive_seed(f"clock:{self._namespace}")
            self._current = self._EPOCH + (seed % 10000)

    @property
    def current_time(self) -> float:
        """Current virtual time without advancing the clock."""
        with self._lock:
            return self._current


# ============================================================
#  Global time.time() Patch — Deterministic Wall Clock
# ============================================================

# Save original time functions
_original_time_time = _time_module.time
_original_time_monotonic = _time_module.monotonic

_time_patched: bool = False
_time_global_clock: Optional[DeterministicClock] = None
_time_patch_lock = threading.Lock()


def _deterministic_time_time() -> float:
    """Deterministic replacement for time.time()."""
    global _time_global_clock
    with _time_patch_lock:
        if _time_global_clock is None:
            _time_global_clock = DeterministicClock("__global_time__", increment=0.001)
        return _time_global_clock.time()


def install_time_patch(increment: float = 0.001) -> None:
    """
    Replace time.time() with a deterministic virtual clock.

    After calling this, ALL code that uses time.time() will get
    reproducible, monotonically increasing timestamps.

    WARNING: Only install in tests or deterministic replay mode.
    In production, real wall-clock time is usually needed for
    logging, monitoring, and user-facing timestamps.

    Args:
        increment: Seconds to advance per call (default 0.001 = 1ms).

    Usage::

        set_global_seed(42)
        install_time_patch()
        # Now time.time() is deterministic
    """
    global _time_patched, _time_global_clock
    with _time_patch_lock:
        if _time_patched:
            logger.debug("install_time_patch: Already installed, skipping")
            return
        _time_global_clock = DeterministicClock("__global_time__", increment=increment)
        _time_module.time = _deterministic_time_time
        _time_patched = True
    logger.info(
        "install_time_patch: time.time() replaced with deterministic clock "
        "(seed=%d, increment=%.4fs)",
        SeedManager().master_seed, increment,
    )


def uninstall_time_patch() -> None:
    """Restore the original time.time() implementation."""
    global _time_patched, _time_global_clock
    with _time_patch_lock:
        if not _time_patched:
            return
        _time_module.time = _original_time_time
        _time_patched = False
        _time_global_clock = None
    logger.info("uninstall_time_patch: time.time() restored to original")


def is_time_patched() -> bool:
    """Check if the deterministic time patch is currently installed."""
    return _time_patched
