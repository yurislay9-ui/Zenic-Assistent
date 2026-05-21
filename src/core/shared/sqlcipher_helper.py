"""
ZENIC-AGENTS - Unified SQLCipher Helper

Centralizes all SQLCipher import logic and connection management.
Tries pysqlcipher3 first (more widely maintained fork), then
sqlcipher3 as fallback, then plain sqlite3 when neither is available.

All other modules should import from this single location so that
SQLCipher library selection is consistent across the project.

Public API:
    is_sqlcipher_available() -> bool
    get_sqlcipher_connection(db_path, passphrase, **kwargs) -> Connection
    encrypt_database(source_path, passphrase) -> str
    sqlcipher_module  – the imported dbapi2 module (or None)
    HAS_SQLCIPHER     – bool flag for quick availability checks
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
from typing import Any, Optional

# ──────────────────────────────────────────────────────────────
#  SQL INJECTION PROTECTION: Identifier validation regex
# ──────────────────────────────────────────────────────────────
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _validate_identifier(name: str, context: str = "") -> None:
    """Validate a SQL identifier (table/column name) to prevent injection.

    Raises ValueError if the name contains characters that could enable
    SQL injection (e.g., quotes, semicolons, whitespace).
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid SQL identifier: {name!r} {context}"
        )

logger = logging.getLogger("zenic_agents.shared.sqlcipher")

# ──────────────────────────────────────────────────────────────
#  LIBRARY RESOLUTION
# ──────────────────────────────────────────────────────────────

sqlcipher_module: Any = None          # Will hold whichever module loaded
_LOADED_LIBRARY: Optional[str] = None # "pysqlcipher3" | "sqlcipher3" | None

try:
    from pysqlcipher3 import dbapi2 as _pysqlcipher  # type: ignore[import-untyped]
    sqlcipher_module = _pysqlcipher
    _LOADED_LIBRARY = "pysqlcipher3"
except ImportError:
    try:
        from sqlcipher3 import dbapi2 as _sqlcipher  # type: ignore[import-untyped]
        sqlcipher_module = _sqlcipher
        _LOADED_LIBRARY = "sqlcipher3"
    except ImportError:
        sqlcipher_module = None
        _LOADED_LIBRARY = None

HAS_SQLCIPHER: bool = sqlcipher_module is not None

if HAS_SQLCIPHER:
    logger.info(
        "SQLCipher helper: using %s for encrypted database connections",
        _LOADED_LIBRARY,
    )
else:
    logger.debug(
        "SQLCipher helper: neither pysqlcipher3 nor sqlcipher3 found; "
        "falling back to plain sqlite3"
    )

# Backward-compatible alias used by db_initializer.py
_HAS_SQLCIPHER: bool = HAS_SQLCIPHER


# ──────────────────────────────────────────────────────────────
#  DEFAULT PRAGMA CONFIGURATION
# ──────────────────────────────────────────────────────────────

_DEFAULT_KDF_ITERATIONS: int = 256_000  # OWASP 2024: ≥256K for PBKDF2-SHA256; matches Rust zenic-pybridge/src/db.rs
_DEFAULT_CIPHER_PAGE_SIZE: int = 4096
_DEFAULT_CIPHER_HMAC: str = "HMAC_SHA256"
_DEFAULT_CIPHER_KDF: str = "PBKDF2_HMAC_SHA256"

_DEFAULT_SQLITE_PRAGMAS: list[tuple[str, str | int]] = [
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("cache_size", -8000),
    ("busy_timeout", 5000),
    ("mmap_size", 67108864),  # 64 MB
]


# ──────────────────────────────────────────────────────────────
#  PUBLIC FUNCTIONS
# ──────────────────────────────────────────────────────────────

def is_sqlcipher_available() -> bool:
    """Return True if any SQLCipher library is importable.

    This is a function (rather than just the module-level ``HAS_SQLCIPHER``)
    so that callers who import early can still get an up-to-date answer.
    """
    return HAS_SQLCIPHER


def get_sqlcipher_connection(
    db_path: str,
    passphrase: str,
    *,
    kdf_iterations: int = _DEFAULT_KDF_ITERATIONS,  # 256K (H-98: was 64K, aligned with Rust)
    cipher_page_size: int = _DEFAULT_CIPHER_PAGE_SIZE,
    row_factory: Any = sqlite3.Row,
    apply_pragmas: bool = True,
    verify: bool = False,
) -> Any:
    """Create an encrypted SQLCipher database connection.

    Tries pysqlcipher3 → sqlcipher3 → plain sqlite3.

    Args:
        db_path: Path to the database file (``":memory:"`` supported).
        passphrase: Encryption key.  If empty, a plain SQLite connection
            is returned regardless of library availability.
        kdf_iterations: PBKDF2 iterations for key derivation.
        cipher_page_size: SQLCipher page size.
        row_factory: sqlite3 row_factory to apply (default: sqlite3.Row).
        apply_pragmas: Whether to apply performance PRAGMAs automatically.
        verify: If True, execute a sanity-check ``SELECT count(*) FROM
            sqlite_master`` to confirm the key is correct.

    Returns:
        A database connection object (encrypted or plain sqlite3).

    Raises:
        RuntimeError: If *verify* is True and the key is incorrect.
    """
    if HAS_SQLCIPHER and passphrase:
        return _open_encrypted(
            db_path,
            passphrase,
            kdf_iterations=kdf_iterations,
            cipher_page_size=cipher_page_size,
            row_factory=row_factory,
            apply_pragmas=apply_pragmas,
            verify=verify,
        )

    # Fallback: plain SQLite
    if passphrase and not HAS_SQLCIPHER:
        logger.warning(
            "SQLCipher not available — database '%s' will be UNENCRYPTED. "
            "Install pysqlcipher3 or sqlcipher3-binary for encryption.",
            db_path,
        )

    return _open_plain(db_path, row_factory=row_factory, apply_pragmas=apply_pragmas)


def encrypt_database(source_path: str, passphrase: str) -> str:
    """Encrypt an existing plain SQLite database with SQLCipher.

    Creates a new encrypted copy alongside the original, then replaces
    the original file with the encrypted version.  A backup of the
    original is kept at ``<source_path>.bak``.

    Args:
        source_path: Path to the plain SQLite database file.
        passphrase: Encryption passphrase for the new database.

    Returns:
        The path of the encrypted database (same as *source_path* on
        success).

    Raises:
        FileNotFoundError: If *source_path* does not exist.
        RuntimeError: If SQLCipher is not available or encryption fails.
    """
    if not HAS_SQLCIPHER:
        raise RuntimeError(
            "SQLCipher is not available. Install pysqlcipher3 or "
            "sqlcipher3-binary to encrypt databases."
        )
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Database not found: {source_path}")
    if not passphrase:
        raise ValueError("A non-empty passphrase is required for encryption.")

    backup_path = source_path + ".bak"
    encrypted_path = source_path + ".enc"

    try:
        # Step 1: backup the original
        shutil.copy2(source_path, backup_path)

        # Step 2: open the plain source for reading
        plain_conn = sqlite3.connect(source_path)

        # Step 3: create encrypted destination
        enc_conn = get_sqlcipher_connection(
            encrypted_path,
            passphrase,
            apply_pragmas=True,
        )

        # Step 4: copy schema + data via ATTACH
        # SECURITY: source_path is validated by caller (must be existing file);
        # we sanitize quotes to prevent breaking out of the string literal.
        safe_path = source_path.replace("'", "''")
        enc_conn.execute(
            f"ATTACH DATABASE '{safe_path}' AS plain_db KEY ''"
        )
        # Export: read from plain, write to encrypted
        tables = plain_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table_name,) in tables:
            # SECURITY: Validate table_name from sqlite_master to prevent injection
            _validate_identifier(table_name, "in encrypt_database table copy")
            enc_conn.execute(
                f"CREATE TABLE IF NOT EXISTS [{table_name}] AS SELECT * FROM plain_db.[{table_name}]"
            )
        enc_conn.execute("DETACH DATABASE plain_db")
        enc_conn.commit()
        enc_conn.close()
        plain_conn.close()

        # Step 5: replace original with encrypted copy
        shutil.move(encrypted_path, source_path)

        logger.info("encrypt_database: encrypted '%s' successfully", source_path)
        return source_path

    except Exception as exc:
        # Restore from backup on failure
        if os.path.isfile(backup_path):
            shutil.move(backup_path, source_path)
        if os.path.isfile(encrypted_path):
            os.remove(encrypted_path)
        logger.error("encrypt_database: failed: %s", exc)
        raise RuntimeError(f"Database encryption failed: {exc}") from exc
    finally:
        # Clean up backup only on success
        if os.path.isfile(backup_path) and os.path.isfile(source_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass


# ──────────────────────────────────────────────────────────────
#  PRIVATE HELPERS
# ──────────────────────────────────────────────────────────────

def _open_encrypted(
    db_path: str,
    passphrase: str,
    *,
    kdf_iterations: int,
    cipher_page_size: int,
    row_factory: Any,
    apply_pragmas: bool,
    verify: bool,
) -> Any:
    """Open an encrypted connection using whichever SQLCipher library loaded."""
    conn = sqlcipher_module.connect(db_path)

    # Set the key — use hex notation for reliability across both libraries
    # SECURITY: PRAGMA statements cannot use ? parameterization in sqlite3.
    # We validate all inputs to prevent injection:
    hex_key = passphrase.encode("utf-8").hex()
    if not all(c in '0123456789abcdef' for c in hex_key):
        raise ValueError("Invalid hex key derived from passphrase")
    conn.execute(f"PRAGMA key = \"x'{hex_key}'\"")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
    if not isinstance(kdf_iterations, int) or kdf_iterations <= 0:
        raise ValueError(f"Invalid kdf_iterations: {kdf_iterations}")
    conn.execute(f"PRAGMA kdf_iter = {kdf_iterations}")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
    if not isinstance(cipher_page_size, int) or cipher_page_size <= 0:
        raise ValueError(f"Invalid cipher_page_size: {cipher_page_size}")
    conn.execute(f"PRAGMA cipher_page_size = {cipher_page_size}")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
    # SECURITY: Validate cipher algorithm names are module-level constants
    # (not user-supplied). These are validated against a whitelist pattern.
    for _algo in (_DEFAULT_CIPHER_HMAC, _DEFAULT_CIPHER_KDF):
        if not _SAFE_IDENTIFIER_RE.match(_algo):
            raise ValueError(f"Invalid cipher algorithm name: {_algo!r}")
    conn.execute(f"PRAGMA cipher_hmac_algorithm = {_DEFAULT_CIPHER_HMAC}")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
    conn.execute(f"PRAGMA cipher_kdf_algorithm = {_DEFAULT_CIPHER_KDF}")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier

    if apply_pragmas:
        _apply_pragmas(conn)

    if verify:
        try:
            conn.execute("SELECT count(*) FROM sqlite_master")  # nosemgrep: sqlalchemy-execute-raw-query
        except Exception as exc:
            conn.close()
            raise RuntimeError(
                f"SQLCipher key verification failed for '{db_path}': {exc}"
            ) from exc

    if row_factory is not None:
        conn.row_factory = row_factory

    logger.info(
        "SQLCipher encrypted connection established (%s, library=%s)",
        db_path,
        _LOADED_LIBRARY,
    )
    return conn


def _open_plain(
    db_path: str,
    *,
    row_factory: Any,
    apply_pragmas: bool,
) -> Any:
    """Open a plain (unencrypted) SQLite connection."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    if apply_pragmas:
        _apply_pragmas(conn)
    if row_factory is not None:
        conn.row_factory = row_factory
    logger.debug("Plain SQLite connection established (%s)", db_path)
    return conn


def _apply_pragmas(conn: Any) -> None:
    """Apply default performance PRAGMAs to a connection.

    SECURITY: PRAGMA statements in sqlite3 do not support ? parameterization.
    We validate each pragma name and value before interpolation to prevent
    SQL injection. Pragma names must be valid identifiers; values must be
    integers or known safe string constants.
    """
    for pragma_name, pragma_value in _DEFAULT_SQLITE_PRAGMAS:
        _validate_identifier(pragma_name, "in _apply_pragmas")
        if isinstance(pragma_value, str):
            if not _SAFE_IDENTIFIER_RE.match(pragma_value):
                raise ValueError(
                    f"Invalid PRAGMA value: {pragma_value!r} for {pragma_name}"
                )
        elif not isinstance(pragma_value, int):
            raise ValueError(
                f"Invalid PRAGMA value type: {type(pragma_value)} for {pragma_name}"
            )
        conn.execute(f"PRAGMA {pragma_name} = {pragma_value}")  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
