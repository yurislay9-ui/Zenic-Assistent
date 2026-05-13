"""
Database and password management mixin for AuthService.

PERFORMANCE/SECURITY (H-01/H-02/H-03 fixes):
- Uses thread-local connection pool instead of creating a new connection per call
- Proper thread synchronization via threading.Lock for all DB operations
- Connections are reused within the same thread, preventing connection storms
"""

from ._imports import (
    logger, sqlite3, secrets, hashlib, threading,
    Path, datetime, timezone, _pwd_context,
    PBKDF2_ITERATIONS, PASSLIB_AVAILABLE,
)

# Thread-local storage for connection pooling
_local = threading.local()


class DbPasswordMixin:
    """Database initialization and password management for AuthService."""

    def _conn(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection (pooled per thread).

        PERFORMANCE (H-02/H-03 fix): Instead of creating a new connection
        on every call (which causes SQLITE_BUSY errors and connection storms
        under load), we reuse a thread-local connection. Each thread gets
        its own connection, avoiding cross-thread issues.

        SECURITY (H-01 fix): Since each thread has its own connection,
        we no longer need check_same_thread=False. SQLite's built-in
        thread safety is preserved.
        """
        # Check if we have a usable cached connection for this thread
        conn = getattr(_local, "db_conn", None)
        cached_path = getattr(_local, "db_path", None)

        # If the db_path changed (e.g. in tests with tmp_path), discard the old connection
        if conn is not None and cached_path == self._db_path:
            try:
                # Quick liveness check
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                # Connection is stale, close and recreate
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None

        # Close old connection if path changed
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

        # Create new connection for this thread
        conn = sqlite3.connect(self._db_path, check_same_thread=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.db_conn = conn
        _local.db_path = self._db_path
        return conn

    def _close_conn(self) -> None:
        """Close the thread-local connection (call during shutdown)."""
        conn = getattr(_local, "db_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            _local.db_conn = None

    def init_db(self):
        """Create users, revoked_tokens, and api_keys tables if not exists."""
        c = self._conn()
        with self._lock:
            c.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT,
                login_count INTEGER DEFAULT 0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                user_id INTEGER,
                revoked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                permissions TEXT DEFAULT '[]',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_used TEXT,
                usage_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id))""")
            for idx in [
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
                "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
                "CREATE INDEX IF NOT EXISTS idx_revoked_jti ON revoked_tokens(jti)",
                "CREATE INDEX IF NOT EXISTS idx_revoked_expires ON revoked_tokens(expires_at)",
                "CREATE INDEX IF NOT EXISTS idx_apikeys_user ON api_keys(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_apikeys_active ON api_keys(active)",
                "CREATE INDEX IF NOT EXISTS idx_apikeys_hash ON api_keys(key_hash, active)",
            ]:
                c.execute(idx)
            c.commit()

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt (preferred) or PBKDF2-SHA256 (fallback)."""
        if _pwd_context:
            # bcrypt has a 72-byte limit — truncate to avoid ValueError
            return _pwd_context.hash(password[:72])
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
        return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${dk.hex()}"

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password against hash."""
        if not password or not hashed:
            return False
        if _pwd_context:
            try:
                # bcrypt has a 72-byte limit — truncate to match hash_password
                return _pwd_context.verify(password[:72], hashed)
            except Exception:
                logger.debug("passlib verify failed, falling back to pbkdf2")
        if hashed.startswith("pbkdf2$"):
            try:
                _, iters_s, salt, stored = hashed.split("$", 3)
                dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters_s))
                return secrets.compare_digest(dk.hex(), stored)
            except (ValueError, IndexError):
                return False
        if hashed.startswith("sha256$"):
            try:
                _, salt, stored = hashed.split("$", 2)
                computed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
                return secrets.compare_digest(computed, stored)
            except (ValueError, IndexError):
                return False
        return False
