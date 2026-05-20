"""
Crypto and Hash API — delegates to native Rust or pure Python fallbacks.

Provides: pbkdf2_derive_key, argon2id_hash, constant_time_compare,
          blake3_hash, xxhash64, merkle_root
"""

from __future__ import annotations

from typing import List

from ._loader import HAS_NATIVE
from .._fallbacks import (
    argon2id_hash as _py_argon2id_hash,
    blake3_hash as _py_blake3_hash,
    constant_time_compare as _py_constant_time_compare,
    merkle_root as _py_merkle_root,
    pbkdf2_derive_key as _py_pbkdf2_derive_key,
    xxhash64 as _py_xxhash64,
)


def pbkdf2_derive_key(
    password: bytes, salt: bytes, iterations: int, key_length: int
) -> bytes:
    if HAS_NATIVE:
        from ._loader import _rust_pbkdf2_derive_key
        return _rust_pbkdf2_derive_key(password, salt, iterations, key_length)
    return _py_pbkdf2_derive_key(password, salt, iterations, key_length)


def argon2id_hash(
    password: bytes,
    salt: bytes,
    memory_cost: int,
    time_cost: int,
    parallelism: int,
) -> bytes:
    if HAS_NATIVE:
        from ._loader import _rust_argon2id_hash
        return _rust_argon2id_hash(
            password, salt, memory_cost, time_cost, parallelism
        )
    return _py_argon2id_hash(
        password, salt, memory_cost, time_cost, parallelism
    )


def constant_time_compare(a: bytes, b: bytes) -> bool:
    if HAS_NATIVE:
        from ._loader import _rust_constant_time_compare
        return _rust_constant_time_compare(a, b)
    return _py_constant_time_compare(a, b)


def blake3_hash(data: bytes) -> str:
    if HAS_NATIVE:
        from ._loader import _rust_blake3_hash
        return _rust_blake3_hash(data)
    return _py_blake3_hash(data)


def xxhash64(data: bytes, seed: int = 0) -> int:
    if HAS_NATIVE:
        from ._loader import _rust_xxhash64
        return _rust_xxhash64(data, seed)
    return _py_xxhash64(data, seed)


def merkle_root(leaves: List[bytes]) -> str:
    if HAS_NATIVE:
        from ._loader import _rust_merkle_root
        return _rust_merkle_root(leaves)
    return _py_merkle_root(leaves)
