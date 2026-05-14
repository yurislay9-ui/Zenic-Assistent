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
    """Pure Python BLAKE3 hash fallback.

    Tries the ``blake3`` Python package. Falls back to SHA-256.

    Parameters
    ----------
    data : bytes
        The data to hash.

    Returns
    -------
    str
        Hex-encoded hash string.
    """
    if not data:
        raise ValueError("data must not be empty")

    try:
        import blake3 as _blake3  # type: ignore[import-untyped]

        return _blake3.blake3(data).hexdigest()
    except ImportError:
        logger.warning(
            "blake3 Python package not available; "
            "falling back to SHA-256. Install 'blake3' or build "
            "the native extension for proper BLAKE3."
        )
        return hashlib.sha256(data).hexdigest()


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
    """Pure Python Merkle root computation.

    Uses SHA-256 when BLAKE3 is not available, or BLAKE3 if installed.

    Parameters
    ----------
    leaves : list[bytes]
        List of leaf values.

    Returns
    -------
    str
        Hex-encoded Merkle root hash.
    """
    if not leaves:
        raise ValueError("leaves must not be empty")

    def _hash_func(data: bytes) -> bytes:
        try:
            import blake3 as _blake3  # type: ignore[import-untyped]

            return _blake3.blake3(data).digest()
        except ImportError:
            return hashlib.sha256(data).digest()

    if len(leaves) == 1:
        return _hash_func(leaves[0]).hex()

    current_level: List[bytes] = [_hash_func(leaf) for leaf in leaves]

    while len(current_level) > 1:
        if len(current_level) % 2 != 0:
            current_level.append(current_level[-1])

        next_level: List[bytes] = []
        for i in range(0, len(current_level), 2):
            combined = current_level[i] + current_level[i + 1]
            next_level.append(_hash_func(combined))
        current_level = next_level

    return current_level[0].hex()
