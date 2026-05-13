"""
Token management mixin for AuthService — JWT, HMAC, revocation.

PERFORMANCE (H-03 fix): Removed per-call connection close() since
connections are now thread-local pooled in DbPasswordMixin._conn().
"""

from ._imports import (
    logger, secrets, json, time, base64, hashlib, hmac, sqlite3,
    datetime, timedelta, timezone, threading,
    JOSE_AVAILABLE, jose_jwt, JWTError, ACCESS_EXPIRE_MIN, REFRESH_EXPIRE_DAYS,
)


class TokenMixin:
    """Token management for AuthService."""

    def create_access_token(self, user_id: int, role: str, extra: dict = None) -> str:
        """Create access token. JWT if jose available, HMAC-based otherwise."""
        jti = secrets.token_hex(16)
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id), "role": role, "type": "access", "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=ACCESS_EXPIRE_MIN)).timestamp()),
        }
        if extra:
            payload.update(extra)
        if JOSE_AVAILABLE:
            return jose_jwt.encode(payload, self._secret_key, algorithm="HS256")
        return self._encode_hmac(payload)

    def create_refresh_token(self, user_id: int) -> str:
        """Create refresh token with longer expiry."""
        jti = secrets.token_hex(16)
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id), "type": "refresh", "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=REFRESH_EXPIRE_DAYS)).timestamp()),
        }
        if JOSE_AVAILABLE:
            return jose_jwt.encode(payload, self._secret_key, algorithm="HS256")
        return self._encode_hmac(payload)

    def verify_token(self, token: str, token_type: str = "access") -> dict:
        """Verify and decode token. Returns payload dict or error dict."""
        payload = None
        if JOSE_AVAILABLE:
            try:
                payload = jose_jwt.decode(token, self._secret_key, algorithms=["HS256"])
            except JWTError:
                payload = None
        if payload is None:
            payload = self._decode_hmac(token)
        if payload is None:
            return {"error": "Invalid or expired token"}
        if payload.get("type") != token_type:
            return {"error": f"Invalid token type: expected {token_type}"}
        if payload.get("exp") and time.time() > payload["exp"]:
            return {"error": "Token has expired"}
        jti = payload.get("jti", "")
        if jti and self.is_token_revoked(jti):
            return {"error": "Token has been revoked"}
        return payload

    def refresh_access_token(self, refresh_token: str) -> dict:
        """Use refresh token to get new access + refresh tokens."""
        payload = self.verify_token(refresh_token, token_type="refresh")
        if "error" in payload:
            return payload
        user_id = int(payload["sub"])
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return {"error": "User account is deactivated"}
        old_jti = payload.get("jti", "")
        if old_jti:
            self.revoke_token(refresh_token)
        return {
            "access_token": self.create_access_token(user_id, user["role"]),
            "refresh_token": self.create_refresh_token(user_id),
            "token_type": "bearer",
        }

    def revoke_token(self, token: str) -> bool:
        """Add token to revocation blacklist."""
        payload = None
        if JOSE_AVAILABLE:
            try:
                payload = jose_jwt.decode(token, self._secret_key, algorithms=["HS256"],
                                          options={"verify_exp": False})
            except JWTError:
                pass
        if payload is None:
            payload = self._decode_hmac(token, verify_exp=False)
        if payload is None:
            return False
        jti = payload.get("jti", "")
        if not jti:
            return False
        exp = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp).isoformat() if exp else None
        now = datetime.now(timezone.utc).isoformat()
        c = self._conn()
        with self._lock:
            try:
                c.execute("INSERT OR IGNORE INTO revoked_tokens (jti, user_id, revoked_at, expires_at) "
                          "VALUES (?, ?, ?, ?)", (jti, int(payload.get("sub", 0)), now, expires_at))
                c.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"AuthService: revoke_token error: {e}")
                return False

    def _encode_hmac(self, payload: dict) -> str:
        """Encode payload using HMAC-SHA256."""
        hdr = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "HMAC-JWT"}, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        sig = hmac.new(self._secret_key.encode(), f"{hdr}.{body}".encode(), hashlib.sha256).hexdigest()
        return f"{hdr}.{body}.{sig}"

    def _decode_hmac(self, token: str, verify_exp: bool = True):
        """Decode HMAC-SHA256 token. Returns payload or None."""
        if not token or token.count(".") != 2:
            return None
        try:
            hdr_b64, body_b64, sig = token.split(".")
            expected = hmac.new(self._secret_key.encode(), f"{hdr_b64}.{body_b64}".encode(),
                               hashlib.sha256).hexdigest()
            if not secrets.compare_digest(sig, expected):
                return None
            pad = 4 - len(body_b64) % 4
            if pad != 4:
                body_b64 += "=" * pad
            payload = json.loads(base64.urlsafe_b64decode(body_b64))
            if verify_exp and payload.get("exp") and time.time() > payload["exp"]:
                return None
            return payload
        except Exception:
            return None

    def _init_revocation_table(self):
        """Ensure revocation table exists (handled by init_db)."""
        pass

    def is_token_revoked(self, token_jti: str) -> bool:
        """Check if a token JTI is in the revocation blacklist."""
        if not token_jti:
            return False
        c = self._conn()
        with self._lock:
            return c.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (token_jti,)).fetchone() is not None

    def cleanup_revoked_tokens(self) -> int:
        """Remove expired tokens from blacklist. Returns count removed."""
        now = datetime.now(timezone.utc).isoformat()
        c = self._conn()
        with self._lock:
            n = c.execute("DELETE FROM revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
                          (now,)).rowcount
            c.commit()
            if n:
                logger.info(f"AuthService: cleaned {n} expired revoked tokens")
            return n
