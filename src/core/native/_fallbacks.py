"""
Pure Python fallback implementations for native Rust functions.

These are used when the ``_zenic_native`` Rust extension is not available.
Each function has the same signature as its Rust counterpart.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
from typing import List

logger = logging.getLogger("zenic_agents.core.native")


def pbkdf2_derive_key(
    password: bytes, salt: bytes, iterations: int, key_length: int
) -> bytes:
    """Pure Python PBKDF2-HMAC-SHA256 key derivation using hashlib.

    Parameters
    ----------
    password : bytes
        The password to derive the key from.
    salt : bytes
        Cryptographic salt.
    iterations : int
        Number of PBKDF2 iterations.
    key_length : int
        Desired output key length in bytes.

    Returns
    -------
    bytes
        The derived key.
    """
    if not password:
        raise ValueError("password must not be empty")
    if not salt:
        raise ValueError("salt must not be empty")
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if key_length <= 0:
        raise ValueError("key_length must be positive")
    return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, key_length)


def argon2id_hash(
    password: bytes,
    salt: bytes,
    memory_cost: int,
    time_cost: int,
    parallelism: int,
) -> bytes:
    """Pure Python Argon2id fallback.

    Tries the ``argon2`` Python package first. If unavailable,
    falls back to PBKDF2 with high iteration count and logs a warning.

    Parameters
    ----------
    password : bytes
        The password to hash.
    salt : bytes
        Cryptographic salt (minimum 8 bytes for argon2-cffi).
    memory_cost : int
        Memory cost in KiB.
    time_cost : int
        Number of passes.
    parallelism : int
        Degree of parallelism.

    Returns
    -------
    bytes
        The raw 32-byte hash.
    """
    if not password:
        raise ValueError("password must not be empty")
    if not salt:
        raise ValueError("salt must not be empty")
    if len(salt) < 8:
        raise ValueError("salt must be at least 8 bytes for Argon2id")
    if memory_cost <= 0:
        raise ValueError("memory_cost must be positive")
    if time_cost <= 0:
        raise ValueError("time_cost must be positive")
    if parallelism <= 0:
        raise ValueError("parallelism must be positive")

    try:
        from argon2 import low_level  # type: ignore[import-untyped]

        return low_level.hash_secret_raw(
            secret=password,
            salt=salt,
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=32,
            type=low_level.Type.ID,
        )
    except ImportError:
        logger.warning(
            "argon2 Python package not available; "
            "falling back to PBKDF2 for argon2id_hash. "
            "Install 'argon2-cffi' or build the native extension."
        )
        derived = hashlib.pbkdf2_hmac(
            "sha256", password, salt, time_cost * 100000, 32
        )
        return derived


def constant_time_compare(a: bytes, b: bytes) -> bool:
    """Pure Python constant-time comparison using hmac.compare_digest.

    Parameters
    ----------
    a : bytes
        First byte string.
    b : bytes
        Second byte string.

    Returns
    -------
    bool
        True if equal, False otherwise.
    """
    return _hmac.compare_digest(a, b)


def blake3_hash(data: bytes) -> str:
    """Pure Python BLAKE3 hash.

    E-04 FIX: BLAKE3 is now MANDATORY — no SHA-256 fallback.
    The Rust native extension (hash.rs) uses blake3::hash() exclusively
    for integrity verification. A SHA-256 fallback would produce different
    hashes, causing cross-language integrity mismatches.

    Requires either the ``_zenic_native`` Rust extension or the ``blake3``
    Python package. Raises RuntimeError if neither is available.

    Parameters
    ----------
    data : bytes
        The data to hash.

    Returns
    -------
    str
        64-character hex-encoded BLAKE3 hash string.
    """
    if not data:
        raise ValueError("data must not be empty")

    try:
        import blake3 as _blake3  # type: ignore[import-untyped]

        return _blake3.blake3(data).hexdigest()
    except ImportError:
        raise RuntimeError(
            "BLAKE3 is mandatory for integrity verification. "
            "Install the 'blake3' Python package or build the "
            "native Rust extension (_zenic_native). "
            "SHA-256 fallback removed (E-04 FIX): it produced "
            "different hashes than the Rust side, causing "
            "cross-language integrity mismatches."
        )


def xxhash64(data: bytes, seed: int) -> int:
    """Pure Python xxHash64 fallback.

    Tries the ``xxhash`` Python package. Falls back to FNV-1a.

    Parameters
    ----------
    data : bytes
        The data to hash.
    seed : int
        A 64-bit seed value.

    Returns
    -------
    int
        The 64-bit hash value.
    """
    if not data:
        raise ValueError("data must not be empty")

    try:
        import xxhash  # type: ignore[import-untyped]

        return xxhash.xxh64(data, seed=seed).intdigest()
    except ImportError:
        logger.warning(
            "xxhash Python package not available; "
            "falling back to FNV-1a. Install 'xxhash' or build "
            "the native extension for proper xxHash64."
        )
        FNV_OFFSET = 14695981039346656037
        FNV_PRIME = 1099511628211
        MASK = (1 << 64) - 1
        h = (FNV_OFFSET ^ seed) & MASK
        for byte in data:
            h ^= byte
            h = (h * FNV_PRIME) & MASK
        return h


def merkle_root(leaves: List[bytes]) -> str:
    """Pure Python Merkle root computation using BLAKE3.

    E-04 FIX: BLAKE3 is now MANDATORY — no SHA-256 fallback.
    The Rust native extension (hash.rs) uses blake3::hash() and
    concatenates raw bytes (not hex strings) for Merkle tree pairing.
    This function matches the Rust behavior exactly.

    Requires either the ``_zenic_native`` Rust extension or the ``blake3``
    Python package. Raises RuntimeError if neither is available.

    Parameters
    ----------
    leaves : list[bytes]
        List of leaf values (raw bytes, typically hashes themselves).

    Returns
    -------
    str
        64-character hex-encoded BLAKE3 Merkle root.
    """
    if not leaves:
        raise ValueError("leaves must not be empty")

    def _hash_func(data: bytes) -> bytes:
        try:
            import blake3 as _blake3  # type: ignore[import-untyped]
            return _blake3.blake3(data).digest()
        except ImportError:
            raise RuntimeError(
                "BLAKE3 is mandatory for Merkle root computation. "
                "Install the 'blake3' Python package or build the "
                "native Rust extension. SHA-256 fallback removed (E-04 FIX)."
            )

    # If only one leaf, its hash is the root (matches Rust hash.rs)
    if len(leaves) == 1:
        return _hash_func(leaves[0]).hex()

    # Build the Merkle tree bottom-up.
    # Each leaf is hashed with BLAKE3, then adjacent hashes are
    # concatenated as RAW BYTES (not hex strings) and re-hashed.
    # This matches the Rust merkle_root() function exactly.
    current_level: List[bytes] = [_hash_func(leaf) for leaf in leaves]

    while len(current_level) > 1:
        # If odd number of nodes, duplicate the last one
        if len(current_level) % 2 != 0:
            current_level.append(current_level[-1])

        next_level: List[bytes] = []
        for i in range(0, len(current_level), 2):
            # E-04 FIX: Concatenate raw bytes, not hex strings.
            # Rust does: combined = left_bytes + right_bytes; blake3(combined)
            # Python was doing: combined = (hex_left + hex_right).encode('utf-8')
            # which produces DIFFERENT hashes than Rust.
            combined = current_level[i] + current_level[i + 1]
            next_level.append(_hash_func(combined))
        current_level = next_level

    return current_level[0].hex()
