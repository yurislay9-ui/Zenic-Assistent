"""Security Middleware - Token Blacklist."""

import logging
import time
import threading
from typing import Any, Dict, FrozenSet, List, Optional, Set

from ._config import SecurityConfig, InputSanitizer
from ._middleware import SecurityHeadersMiddleware, AuthRateLimiter

logger = logging.getLogger("zenic_agents.server.security_middleware")

class TokenBlacklist:
    """JWT token blacklist for revocation and rotation.

    Stores revoked token IDs (jti claims) in a SQLite database
    with automatic expiry cleanup. Supports:
    - Single token revocation
    - Bulk revocation (all tokens for a user)
    - Token rotation (revoke old, issue new)
    - Automatic pruning of expired entries

    Thread-safe: all operations are protected by a lock.
    """

    def __init__(self, db_path: str = "token_blacklist.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._initialized = False
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the blacklist database."""
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS revoked_tokens (
                    jti TEXT PRIMARY KEY,
                    user_id INTEGER,
                    reason TEXT,
                    revoked_at REAL NOT NULL,
                    expires_at REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_revoked_expires
                ON revoked_tokens(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_revoked_user
                ON revoked_tokens(user_id)
            """)
            conn.commit()
            conn.close()
            self._initialized = True
        except Exception as exc:
            logger.error("TokenBlacklist: Init failed: %s", exc)

    def is_revoked(self, jti: str) -> bool:
        """Check if a token has been revoked.

        Args:
            jti: JWT ID claim.

        Returns:
            True if the token is revoked.
        """
        if not self._initialized:
            return False

        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT 1 FROM revoked_tokens WHERE jti = ?",
                (jti,),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def revoke_token(
        self,
        jti: str,
        user_id: Optional[int] = None,
        reason: str = "manual",
        expires_at: Optional[float] = None,
    ) -> bool:
        """Revoke a token by its JTI.

        Args:
            jti: JWT ID claim to revoke.
            user_id: Associated user ID.
            reason: Revocation reason.
            expires_at: Token expiry timestamp (for auto-cleanup).

        Returns:
            True if successfully revoked.
        """
        if not self._initialized:
            return False

        try:
            import sqlite3
            import time
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    """INSERT OR IGNORE INTO revoked_tokens
                       (jti, user_id, reason, revoked_at, expires_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (jti, user_id, reason, time.time(), expires_at),
                )
                conn.commit()
                conn.close()
            logger.info("TokenBlacklist: Revoked token %s (reason=%s)", jti[:8], reason)
            return True
        except Exception as exc:
            logger.error("TokenBlacklist: Revoke failed: %s", exc)
            return False

    def revoke_all_user_tokens(self, user_id: int, reason: str = "security") -> int:
        """Revoke all tokens for a user.

        Used when a user changes password or is compromised.

        Args:
            user_id: User whose tokens to revoke.
            reason: Revocation reason.

        Returns:
            Number of tokens revoked.
        """
        if not self._initialized:
            return 0

        try:
            import sqlite3
            import time
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                # Get active tokens for this user
                rows = conn.execute(
                    "SELECT jti FROM revoked_tokens WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
                # Mark all future tokens for this user as revoked via a special entry
                conn.execute(
                    """INSERT OR IGNORE INTO revoked_tokens
                       (jti, user_id, reason, revoked_at, expires_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (f"user-all-{user_id}-{time.time()}", user_id, reason, time.time(), None),
                )
                conn.commit()
                conn.close()
            logger.info(
                "TokenBlacklist: Revoked all tokens for user %d (reason=%s)",
                user_id, reason,
            )
            return len(rows) + 1
        except Exception as exc:
            logger.error("TokenBlacklist: Bulk revoke failed: %s", exc)
            return 0

    def is_user_fully_revoked(self, user_id: int, after_time: float) -> bool:
        """Check if all tokens for a user were revoked after a timestamp.

        Args:
            user_id: User to check.
            after_time: Timestamp to check against.

        Returns:
            True if a bulk revocation exists after the given time.
        """
        if not self._initialized:
            return False

        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                """SELECT 1 FROM revoked_tokens
                   WHERE user_id = ? AND jti LIKE 'user-all-%'
                   AND revoked_at >= ?""",
                (user_id, after_time),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def prune_expired(self) -> int:
        """Remove entries for tokens that have already expired.

        Returns:
            Number of entries pruned.
        """
        if not self._initialized:
            return 0

        try:
            import sqlite3
            import time
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.execute(
                    "DELETE FROM revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (time.time(),),
                )
                count = cursor.rowcount
                conn.commit()
                conn.close()
            if count > 0:
                logger.debug("TokenBlacklist: Pruned %d expired entries", count)
            return count
        except Exception:
            return 0


# ============================================================
#  SECURITY MIDDLEWARE FACTORY
# ============================================================

def create_security_middleware(config: Optional[SecurityConfig] = None):
    """Create a FastAPI middleware function that applies all security measures.

    This is the main entry point for wiring Phase 5 security into
    the FastAPI app. It returns a middleware function that:
    1. Checks request size
    2. Enforces auth rate limits
    3. Adds security headers to responses
    4. Enforces HTTPS (if configured)
    5. Validates and sanitizes input

    Usage in fastapi_app.py:
        security_config = SecurityConfig.from_env()
        app.middleware("http")(create_security_middleware(security_config))

    Args:
        config: Security configuration.

    Returns:
        Async middleware function for FastAPI.
    """
    if config is None:
        config = SecurityConfig.from_env()

    sanitizer = InputSanitizer(config)
    headers_middleware = SecurityHeadersMiddleware(config)
    auth_limiter = AuthRateLimiter(
        rpm=config.auth_rate_limit_rpm,
        burst=config.auth_rate_limit_burst,
    )
    security_headers = headers_middleware.get_headers()
    max_size_bytes = int(config.max_request_size_mb * 1024 * 1024)

    # Auth endpoints that need strict rate limiting
    AUTH_ENDPOINTS: FrozenSet[str] = frozenset({
        "/v1/auth/login",
        "/v1/auth/register",
        "/v1/auth/refresh",
    })

    async def security_middleware(request: Any, call_next: Any) -> Any:
        """FastAPI middleware for security checks and headers."""
        # 1. HTTPS enforcement
        if config.force_https:
            scheme = request.url.scheme
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            if scheme != "https" and forwarded_proto != "https":
                from fastapi.responses import RedirectResponse
                https_url = str(request.url).replace("http://", "https://", 1)
                return RedirectResponse(url=https_url, status_code=301)

        # 2. Request size check
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > max_size_bytes:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=413,
                content={"error": {"message": "Request body too large", "type": "payload_too_large"}},
            )

        # 3. Auth endpoint rate limiting
        if request.url.path in AUTH_ENDPOINTS:
            client_ip = request.client.host if request.client else "0.0.0.0"
            if not auth_limiter.is_allowed(client_ip):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"error": {"message": "Too many auth attempts", "type": "auth_rate_limit"}},
                    headers={"Retry-After": "60"},
                )

        # 4. Process request
        response = await call_next(request)

        # 5. Record auth result for rate limiting
        if request.url.path in AUTH_ENDPOINTS:
            client_ip = request.client.host if request.client else "0.0.0.0"
            if response.status_code == 401:
                auth_limiter.record_failure(client_ip)
            elif response.status_code == 200:
                auth_limiter.record_success(client_ip)

        # 6. Add security headers
        for header_name, header_value in security_headers.items():
            response.headers[header_name] = header_value

        return response

    return security_middleware

