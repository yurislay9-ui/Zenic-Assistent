"""
ZENIC-AGENTS v16 - Security Middleware (Phase 5)

Comprehensive security middleware stack for FastAPI:
- Input sanitization (XSS, injection prevention)
- Security headers (CSP, X-Frame-Options, HSTS, etc.)
- Configurable CORS per environment
- Request size limiting
- HTTPS enforcement
- Auth endpoint rate limiting (brute-force protection)
- Token blacklisting/revocation

All components are configurable and can be selectively enabled/disabled
via environment variables or constructor parameters.
"""

import html
import logging
import os
import re
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger("zenic_agents.server.security_middleware")

__all__ = [
    "SecurityConfig",
    "InputSanitizer",
    "SecurityHeadersMiddleware",
    "AuthRateLimiter",
    "TokenBlacklist",
    "create_security_middleware",
]


# ============================================================
#  SECURITY CONFIGURATION
# ============================================================

@dataclass
class SecurityConfig:
    """Centralized security configuration.

    All settings can be overridden via environment variables.

    Attributes:
        cors_origins: Allowed CORS origins (comma-separated).
        cors_allow_credentials: Whether to allow credentials.
        enable_csp: Whether to add Content-Security-Policy header.
        enable_hsts: Whether to add Strict-Transport-Security header.
        hsts_max_age: HSTS max-age in seconds.
        force_https: Whether to redirect HTTP to HTTPS.
        max_request_size_mb: Maximum request body size in MB.
        max_input_length: Maximum string input length.
        sanitize_html: Whether to HTML-escape string inputs.
        auth_rate_limit_rpm: Rate limit for auth endpoints (per IP).
        auth_rate_limit_burst: Burst size for auth rate limiting.
        token_blacklist_enabled: Whether to check token blacklist.
        token_blacklist_db: Path to token blacklist database.
    """
    # CORS
    cors_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_max_age: int = 600

    # Security Headers
    enable_csp: bool = True
    csp_policy: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    enable_hsts: bool = True
    hsts_max_age: int = 31536000  # 1 year
    force_https: bool = False

    # Input Validation
    max_request_size_mb: float = 10.0
    max_input_length: int = 10000
    sanitize_html: bool = True

    # Auth Rate Limiting
    auth_rate_limit_rpm: int = 20
    auth_rate_limit_burst: int = 5

    # Token Blacklist
    token_blacklist_enabled: bool = True
    token_blacklist_db: str = "token_blacklist.sqlite"

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Create config from environment variables."""
        return cls(
            cors_origins=os.getenv("ZENIC_CORS_ORIGINS", "*"),
            cors_allow_credentials=os.getenv("ZENIC_CORS_CREDENTIALS", "true").lower() == "true",
            enable_csp=os.getenv("ZENIC_CSP_ENABLED", "true").lower() == "true",
            enable_hsts=os.getenv("ZENIC_HSTS_ENABLED", "true").lower() == "true",
            force_https=os.getenv("ZENIC_FORCE_HTTPS", "false").lower() == "true",
            max_request_size_mb=float(os.getenv("ZENIC_MAX_REQUEST_SIZE_MB", "10")),
            auth_rate_limit_rpm=int(os.getenv("ZENIC_AUTH_RATE_LIMIT_RPM", "20")),
            auth_rate_limit_burst=int(os.getenv("ZENIC_AUTH_RATE_LIMIT_BURST", "5")),
            token_blacklist_enabled=os.getenv("ZENIC_TOKEN_BLACKLIST", "true").lower() == "true",
        )

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# ============================================================
#  INPUT SANITIZER
# ============================================================

class InputSanitizer:
    """Sanitizes user input to prevent XSS and injection attacks.

    Provides multiple sanitization strategies:
    - HTML escaping (prevents XSS)
    - SQL pattern detection (flags potential SQL injection)
    - Path traversal detection
    - Length limiting
    - Null byte removal

    Can be used as a FastAPI middleware or called directly.
    """

    # Patterns that indicate potential attacks
    SQL_INJECTION_PATTERNS: List[re.Pattern] = [
        re.compile(r"(?i)(\b(union\s+select|select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|alter\s+table)\b)"),
        re.compile(r"(?i)(--|;|--\s*$|/\*|\*/)"),
        re.compile(r"(?i)(\b(exec|execute|xp_)\b)"),
    ]

    XSS_PATTERNS: List[re.Pattern] = [
        re.compile(r"<\s*script", re.IGNORECASE),
        re.compile(r"javascript\s*:", re.IGNORECASE),
        re.compile(r"on(error|load|click|mouseover|focus|blur)\s*=", re.IGNORECASE),
        re.compile(r"<\s*iframe", re.IGNORECASE),
        re.compile(r"<\s*object", re.IGNORECASE),
        re.compile(r"<\s*embed", re.IGNORECASE),
    ]

    PATH_TRAVERSAL_PATTERN: re.Pattern = re.compile(r"(\.\./|\.\.\\|%2e%2e%2f|%2e%2e/)", re.IGNORECASE)

    def __init__(self, config: Optional[SecurityConfig] = None) -> None:
        self._config = config or SecurityConfig()

    def sanitize_string(self, value: str) -> str:
        """Sanitize a string input.

        Applies:
        1. Null byte removal
        2. Length limiting
        3. HTML escaping (if configured)

        Args:
            value: Raw string input.

        Returns:
            Sanitized string.
        """
        # Remove null bytes
        value = value.replace("\x00", "")

        # Length limit
        if len(value) > self._config.max_input_length:
            value = value[:self._config.max_input_length]

        # HTML escaping
        if self._config.sanitize_html:
            value = html.escape(value, quote=True)

        return value

    def check_sql_injection(self, value: str) -> bool:
        """Check if a string matches SQL injection patterns.

        Args:
            value: String to check.

        Returns:
            True if potential SQL injection detected.
        """
        for pattern in self.SQL_INJECTION_PATTERNS:
            if pattern.search(value):
                return True
        return False

    def check_xss(self, value: str) -> bool:
        """Check if a string matches XSS patterns.

        Args:
            value: String to check.

        Returns:
            True if potential XSS detected.
        """
        for pattern in self.XSS_PATTERNS:
            if pattern.search(value):
                return True
        return False

    def check_path_traversal(self, value: str) -> bool:
        """Check if a string contains path traversal attempts.

        Args:
            value: String to check.

        Returns:
            True if path traversal detected.
        """
        return bool(self.PATH_TRAVERSAL_PATTERN.search(value))

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize all string values in a dict.

        Args:
            data: Dictionary with potentially unsanitized values.

        Returns:
            Dictionary with sanitized values.
        """
        result: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.sanitize_string(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.sanitize_string(item) if isinstance(item, str)
                    else self.sanitize_dict(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def validate_request_body(self, body: Dict[str, Any]) -> Optional[str]:
        """Validate a request body for security threats.

        Returns None if safe, or an error message string if threats detected.
        Does NOT sanitize — only validates. Use sanitize_dict() to sanitize.

        Args:
            body: Request body dict.

        Returns:
            Error message or None if safe.
        """
        all_text = self._extract_all_text(body)

        for text in all_text:
            if self.check_sql_injection(text):
                return "Potential SQL injection detected"
            if self.check_path_traversal(text):
                return "Path traversal attempt detected"
            # Note: XSS check is informational — we escape, not reject

        return None

    def _extract_all_text(self, data: Any) -> List[str]:
        """Extract all string values from nested data structures."""
        texts: List[str] = []
        if isinstance(data, str):
            texts.append(data)
        elif isinstance(data, dict):
            for v in data.values():
                texts.extend(self._extract_all_text(v))
        elif isinstance(data, list):
            for item in data:
                texts.extend(self._extract_all_text(item))
        return texts


# ============================================================
#  SECURITY HEADERS MIDDLEWARE
# ============================================================

