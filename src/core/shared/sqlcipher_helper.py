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
import shutil
import sqlite3
from typing import Any, Optional

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

_DEFAULT_KDF_ITERATIONS: int = 64_000
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
    kdf_iterations: int = _DEFAULT_KDF_ITERATIONS,
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
        enc_conn.execute(
            f"ATTACH DATABASE '{source_path}' AS plain_db KEY ''"
        )
        # Export: read from plain, write to encrypted
        tables = plain_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (table_name,) in tables:
            enc_conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM plain_db.{table_name}"
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
    hex_key = passphrase.encode("utf-8").hex()
    conn.execute(f"PRAGMA key = \"x'{hex_key}'\"")
    conn.execute(f"PRAGMA kdf_iter = {kdf_iterations}")
    conn.execute(f"PRAGMA cipher_page_size = {cipher_page_size}")
    conn.execute(f"PRAGMA cipher_hmac_algorithm = {_DEFAULT_CIPHER_HMAC}")
    conn.execute(f"PRAGMA cipher_kdf_algorithm = {_DEFAULT_CIPHER_KDF}")

    if apply_pragmas:
        _apply_pragmas(conn)

    if verify:
        try:
            conn.execute("SELECT count(*) FROM sqlite_master")
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
    """Apply default performance PRAGMAs to a connection."""
    for pragma_name, pragma_value in _DEFAULT_SQLITE_PRAGMAS:
        conn.execute(f"PRAGMA {pragma_name} = {pragma_value}")
