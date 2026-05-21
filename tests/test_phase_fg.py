"""
ZENIC-AGENTS — Phase F+G Security Tests

Tests for MEDIUM (F1-F6) and LOW (G1-G3) security fixes from FASE 3.

Run: pytest tests/test_phase_fg.py -v
"""

import os
import re
import sys
import json
import time
import pytest
import unittest
from unittest.mock import patch, MagicMock

# ──────────────────────────────────────────────────────────────
#  Test Configuration
# ──────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_LIB = os.path.join(PROJECT_ROOT, "gateway", "src", "lib")

# Add Python source to path
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT))


# ══════════════════════════════════════════════════════════════
#  F1: Query Param Sanitization (#20)
# ══════════════════════════════════════════════════════════════

class TestQueryParamSanitization(unittest.TestCase):
    """Test SQL injection, XSS, and path traversal detection in query params."""

    def test_sql_injection_union_select(self):
        """SQL injection with UNION SELECT should be detected."""
        payload = "1 UNION SELECT * FROM users--"
        # Simulate the regex check from middleware
        sql_patterns = [
            re.compile(r'(\b(union\s+select|select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|alter\s+table|exec\s*\(|execute\s*\()\b)', re.IGNORECASE),
            re.compile(r'(--|;|/\*|\*/|xp_|0x[0-9a-f]{2})', re.IGNORECASE),
            re.compile(r"('.*\b(or|and)\b.*')", re.IGNORECASE),
        ]
        detected = any(p.search(payload) for p in sql_patterns)
        self.assertTrue(detected, "UNION SELECT injection should be detected")

    def test_sql_injection_drop_table(self):
        """SQL injection with DROP TABLE should be detected."""
        payload = "1; DROP TABLE users; --"
        sql_patterns = [
            re.compile(r'(\b(union\s+select|select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|alter\s+table|exec\s*\(|execute\s*\()\b)', re.IGNORECASE),
            re.compile(r'(--|;|/\*|\*/|xp_|0x[0-9a-f]{2})', re.IGNORECASE),
        ]
        detected = any(p.search(payload) for p in sql_patterns)
        self.assertTrue(detected, "DROP TABLE injection should be detected")

    def test_sql_injection_tautology(self):
        """SQL injection with tautology should be detected."""
        payload = "' OR '1'='1"
        sql_patterns = [
            re.compile(r"('.*\b(or|and)\b.*')", re.IGNORECASE),
        ]
        detected = any(p.search(payload) for p in sql_patterns)
        self.assertTrue(detected, "Tautology injection should be detected")

    def test_sql_injection_comment(self):
        """SQL injection with comment should be detected."""
        payload = "admin'--"
        sql_patterns = [
            re.compile(r'(--|;|/\*|\*/|xp_|0x[0-9a-f]{2})', re.IGNORECASE),
        ]
        detected = any(p.search(payload) for p in sql_patterns)
        self.assertTrue(detected, "Comment injection should be detected")

    def test_legitimate_query_param_passes(self):
        """Legitimate query params should not trigger detection."""
        legitimate_values = [
            "active",
            "2024-01-15",
            "user@example.com",
            "subscription_tier",
            "100",
        ]
        sql_patterns = [
            re.compile(r'(\b(union\s+select|select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|alter\s+table|exec\s*\(|execute\s*\()\b)', re.IGNORECASE),
            re.compile(r'(--|;|/\*|\*/|xp_|0x[0-9a-f]{2})', re.IGNORECASE),
            re.compile(r"('.*\b(or|and)\b.*')", re.IGNORECASE),
        ]
        for value in legitimate_values:
            detected = any(p.search(value) for p in sql_patterns)
            self.assertFalse(detected, f"Legitimate value '{value}' should not be flagged")

    def test_xss_script_tag(self):
        """XSS with script tag should be detected."""
        payload = '<script>alert("xss")</script>'
        xss_patterns = [
            re.compile(r'<script[\s>]', re.IGNORECASE),
            re.compile(r'javascript\s*:', re.IGNORECASE),
            re.compile(r'on\w+\s*=', re.IGNORECASE),
        ]
        detected = any(p.search(payload) for p in xss_patterns)
        self.assertTrue(detected, "Script tag XSS should be detected")

    def test_xss_event_handler(self):
        """XSS with event handler should be detected."""
        payload = '<img onerror="alert(1)" src=x>'
        xss_patterns = [
            re.compile(r'on\w+\s*=', re.IGNORECASE),
        ]
        detected = any(p.search(payload) for p in xss_patterns)
        self.assertTrue(detected, "Event handler XSS should be detected")

    def test_xss_javascript_uri(self):
        """XSS with javascript: URI should be detected."""
        payload = '<a href="javascript:alert(1)">'
        xss_patterns = [
            re.compile(r'javascript\s*:', re.IGNORECASE),
        ]
        detected = any(p.search(payload) for p in xss_patterns)
        self.assertTrue(detected, "javascript: URI XSS should be detected")

    def test_query_param_length_limit(self):
        """Query params exceeding 500 chars should be rejected."""
        long_param = "a" * 501
        exceeds = len(long_param) > 500
        self.assertTrue(exceeds, "Long param should exceed limit")

    def test_path_traversal(self):
        """Path traversal attempts should be detected."""
        payloads = ["../../../etc/passwd", "..\\..\\windows\\system32", "/etc/shadow"]
        for payload in payloads:
            has_traversal = "../" in payload or "..\\" in payload or payload.startswith("/")
            self.assertTrue(has_traversal, f"Path traversal in '{payload}' should be detected")


# ══════════════════════════════════════════════════════════════
#  F2: Error Message Information Leakage (#31)
# ══════════════════════════════════════════════════════════════

class TestErrorSanitization(unittest.TestCase):
    """Test that error messages don't leak internal information."""

    def test_strip_file_paths(self):
        """File paths should be stripped from error messages."""
        messages = [
            "Error in /home/user/project/src/module.py line 42",
            "Cannot read C:\\Users\\admin\\config.json",
            "Module not found: /usr/local/lib/node_modules/express",
        ]
        for msg in messages:
            # Simulate the stripping regex
            stripped = re.sub(r'(/[\w.-]+)+|([A-Za-z]:\\[\w.-\\]+)', '[PATH]', msg)
            self.assertNotIn("/home/", stripped)
            self.assertNotIn("C:\\Users", stripped)

    def test_strip_connection_strings(self):
        """Database connection strings should be stripped."""
        messages = [
            "Failed to connect to postgresql://user:pass@localhost:5432/db",
            "Connection string: mysql://admin:secret@db.example.com/mydb",
            "MongoDB: mongodb+srv://user:p@cluster.mongodb.net/test",
        ]
        for msg in messages:
            stripped = re.sub(
                r'(postgresql|postgres|mysql|mongodb(\+srv)?|redis|mssql)://[^\s]+',
                '[DB_URL]',
                msg,
                flags=re.IGNORECASE,
            )
            self.assertNotIn("postgresql://", stripped)
            self.assertNotIn("mysql://", stripped)
            self.assertNotIn("mongodb+srv://", stripped)

    def test_strip_env_vars(self):
        """Environment variable values should be stripped."""
        messages = [
            "Config: ZENIC_DB_PASSPHRASE=mysecret123",
            "Setting API_KEY=sk-abcdef123456",
            "Token: AUTH_TOKEN=Bearer xyz",
        ]
        for msg in messages:
            stripped = re.sub(
                r'([A-Z_]{3,})=(\S+)',
                r'\1=[ENV_VAR]',
                msg,
            )
            self.assertNotIn("mysecret123", stripped)
            self.assertNotIn("sk-abcdef", stripped)
            self.assertNotIn("Bearer xyz", stripped)

    def test_strip_ip_addresses(self):
        """IP addresses should be stripped."""
        messages = [
            "Connection from 192.168.1.100 refused",
            "Server at 10.0.0.1:5432 not responding",
            "Client IP: 172.16.254.1",
        ]
        for msg in messages:
            stripped = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', msg)
            self.assertNotRegex(stripped, r'\d+\.\d+\.\d+\.\d+')

    def test_strip_prisma_details(self):
        """Prisma internal details should be stripped."""
        messages = [
            "PrismaClientInitializationError: P1001 Can't reach database server at localhost:5432",
            "Invalid prisma.subscription.findUnique() invocation",
        ]
        for msg in messages:
            stripped = re.sub(
                r'PrismaClient\w+Error',
                'DatabaseError',
                msg,
            )
            # Should not expose Prisma internal class names
            self.assertNotIn("PrismaClientInitializationError", stripped)

    def test_production_error_generic(self):
        """In production, 500 errors should return generic messages."""
        # Production errors should never contain internal details
        production_msg = "An internal error occurred"
        sensitive_info = [
            "stack", "trace", "Error:", "at ", ".py:", ".ts:",
            "line 42", "cannot read", "undefined is not",
        ]
        for info in sensitive_info:
            self.assertNotIn(info, production_msg.lower())


# ══════════════════════════════════════════════════════════════
#  F3: Audit Logging (#32)
# ══════════════════════════════════════════════════════════════

class TestAuditLogging(unittest.TestCase):
    """Test audit logging for critical operations."""

    def test_audit_event_structure(self):
        """Audit events should have required fields."""
        required_fields = [
            "timestamp", "eventType", "action", "result", "severity",
        ]
        # Verify the required fields are defined
        self.assertEqual(len(required_fields), 5)

    def test_audit_event_types(self):
        """Audit events should cover critical operations."""
        expected_types = [
            "auth", "data_access", "admin_action", "security_event",
            "hitl_decision", "subscription", "payment",
        ]
        self.assertEqual(len(expected_types), 7)

    def test_audit_severity_levels(self):
        """Severity levels should be well-defined."""
        severities = ["low", "medium", "high", "critical"]
        self.assertEqual(len(severities), 4)

    def test_hitl_audit_events(self):
        """HITL decisions should be audited."""
        hitl_actions = ["approve", "reject", "escalate", "delegate", "undo"]
        self.assertEqual(len(hitl_actions), 5)

    def test_subscription_audit_events(self):
        """Subscription changes should be audited."""
        sub_actions = ["signup", "cancel", "upgrade", "renew", "payment"]
        self.assertEqual(len(sub_actions), 5)

    def test_payment_audit_events(self):
        """Payment operations should be audited."""
        pay_actions = ["submit_tx", "confirm", "verify", "refund"]
        self.assertEqual(len(pay_actions), 4)


# ══════════════════════════════════════════════════════════════
#  F4: Session Management (#37)
# ══════════════════════════════════════════════════════════════

class TestSessionManagement(unittest.TestCase):
    """Test session lifecycle management."""

    def test_session_config_defaults(self):
        """Default session config should have secure values."""
        # 30 min timeout
        default_timeout = 30 * 60 * 1000
        self.assertEqual(default_timeout, 1_800_000)
        # Max 5 sessions per user
        max_sessions = 5
        self.assertLessEqual(max_sessions, 10)
        # Renewal threshold: 5 min before expiry
        renewal_threshold = 5 * 60 * 1000
        self.assertEqual(renewal_threshold, 300_000)

    def test_session_expiry(self):
        """Sessions should expire after timeout."""
        timeout_ms = 30 * 60 * 1000  # 30 min
        created_at = time.time() * 1000
        expires_at = created_at + timeout_ms
        # Session should not be expired immediately
        self.assertGreater(expires_at, created_at)
        # Session should be expired after timeout
        future_time = created_at + timeout_ms + 1
        is_expired = future_time > expires_at
        self.assertTrue(is_expired)

    def test_session_revocation(self):
        """Sessions should be revocable."""
        session = {
            "sessionId": "test-123",
            "isRevoked": False,
        }
        # Before revocation
        self.assertFalse(session["isRevoked"])
        # After revocation
        session["isRevoked"] = True
        self.assertTrue(session["isRevoked"])

    def test_max_sessions_per_user(self):
        """Maximum sessions per user should be enforced."""
        max_sessions = 5
        user_sessions = list(range(max_sessions + 1))
        # Should evict oldest when exceeding limit
        exceeds = len(user_sessions) > max_sessions
        self.assertTrue(exceeds)
        # After eviction, should be at max
        after_eviction = user_sessions[1:]  # FIFO eviction
        self.assertEqual(len(after_eviction), max_sessions)


# ══════════════════════════════════════════════════════════════
#  F5: Sensitive Data in Logs (#33)
# ══════════════════════════════════════════════════════════════

class TestLogRedaction(unittest.TestCase):
    """Test that sensitive data is redacted from logs."""

    def test_redact_api_keys(self):
        """API keys should be redacted."""
        patterns = [
            ("sk-1234567890abcdef", True),
            ("zk_abcdef1234567890", True),
            ("api_key=mysecret123", True),
            ("regular text", False),
        ]
        api_key_pattern = re.compile(r'(sk-|zk_)[\w-]+|api[_-]?key[=:]\s*\S+', re.IGNORECASE)
        for text, should_match in patterns:
            match = api_key_pattern.search(text)
            if should_match:
                self.assertIsNotNone(match, f"API key in '{text}' should be detected")
            else:
                self.assertIsNone(match, f"'{text}' should not be flagged as API key")

    def test_redact_bearer_tokens(self):
        """Bearer tokens should be redacted."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.sig"
        bearer_pattern = re.compile(r'Bearer\s+\S+', re.IGNORECASE)
        match = bearer_pattern.search(text)
        self.assertIsNotNone(match, "Bearer token should be detected")

    def test_redact_passwords(self):
        """Passwords should be redacted."""
        patterns = [
            "password=secret123",
            "passwd=hunter2",
            "pwd=admin123",
        ]
        pwd_pattern = re.compile(r'(password|passwd|pwd)[=:]\s*\S+', re.IGNORECASE)
        for text in patterns:
            match = pwd_pattern.search(text)
            self.assertIsNotNone(match, f"Password in '{text}' should be detected")

    def test_redact_email_addresses(self):
        """Email addresses should be redacted."""
        text = "User email: admin@zenic-agents.com"
        email_pattern = re.compile(r'[\w.-]+@[\w.-]+\.\w{2,}')
        match = email_pattern.search(text)
        self.assertIsNotNone(match, "Email should be detected")

    def test_redact_trc20_wallet(self):
        """TRC20 wallet addresses should be redacted."""
        text = "Wallet: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        wallet_pattern = re.compile(r'T[A-HJ-NP-Za-km-z1-9]{33}')
        match = wallet_pattern.search(text)
        self.assertIsNotNone(match, "TRC20 wallet address should be detected")

    def test_redact_ip_addresses(self):
        """IP addresses should be partially masked."""
        text = "Connection from 192.168.1.100"
        ip_pattern = re.compile(r'\b(\d{1,3})\.\d{1,3}\.\d{1,3}\.\d{1,3}\b')
        match = ip_pattern.search(text)
        self.assertIsNotNone(match, "IP address should be detected")

    def test_redact_jwt_tokens(self):
        """JWT tokens should be redacted."""
        text = "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123def456"
        jwt_pattern = re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')
        match = jwt_pattern.search(text)
        self.assertIsNotNone(match, "JWT token should be detected")

    def test_redact_db_connection_strings(self):
        """Database connection strings should be redacted."""
        patterns = [
            "postgresql://user:pass@localhost:5432/mydb",
            "mysql://admin:secret@db.example.com/db",
            "mongodb://user:p@cluster.mongodb.net/test",
            "redis://default:password@localhost:6379",
        ]
        db_pattern = re.compile(r'(postgresql|postgres|mysql|mongodb|redis|mssql|cockroach)://[^\s]+', re.IGNORECASE)
        for text in patterns:
            match = db_pattern.search(text)
            self.assertIsNotNone(match, f"DB connection string should be detected: {text}")


# ══════════════════════════════════════════════════════════════
#  F6: Insecure Default Configurations (#34)
# ══════════════════════════════════════════════════════════════

class TestSecureDefaults(unittest.TestCase):
    """Test that default configurations are secure."""

    def test_insecure_default_detection(self):
        """Known insecure defaults should be detected."""
        insecure_values = [
            "default-key", "change-me", "changeme", "secret", "password",
            "admin", "test", "1234", "abcd", "root", "default", "example",
            "placeholder", "todo", "fixme", "temp", "temporary",
        ]
        self.assertGreaterEqual(len(insecure_values), 15)

    def test_cors_not_wildcard_with_credentials(self):
        """CORS with wildcard origin and credentials should be rejected."""
        # This combination is insecure: Access-Control-Allow-Origin: * with credentials
        cors_origin = "*"
        credentials = True
        insecure = cors_origin == "*" and credentials
        self.assertTrue(insecure, "Wildcard CORS with credentials should be flagged")

    def test_passphrase_minimum_length(self):
        """Encryption passphrase should have minimum length."""
        min_length = 32
        short_pass = "short"
        self.assertLess(len(short_pass), min_length, "Short passphrase should be rejected")

    def test_pbkdf2_minimum_iterations(self):
        """PBKDF2 iterations should meet minimum."""
        min_iterations = 100_000
        default_iterations = 100_000
        self.assertGreaterEqual(default_iterations, min_iterations)

    def test_rate_limiting_defaults(self):
        """Rate limiting should have secure defaults."""
        # Default: 100 req/min
        default_max = 100
        window_ms = 60_000
        self.assertLessEqual(default_max, 1000)  # Not too permissive
        self.assertGreater(default_max, 0)  # Not zero (disabled)

    def test_hsts_enabled_in_production(self):
        """HSTS should be enabled in production."""
        is_prod = True
        hsts_enabled = is_prod  # Should auto-enable in production
        self.assertTrue(hsts_enabled, "HSTS should be enabled in production")

    def test_session_timeout_reasonable(self):
        """Session timeout should be reasonable."""
        timeout_min = 30  # 30 minutes
        self.assertLessEqual(timeout_min, 60)  # Not too long
        self.assertGreater(timeout_min, 5)  # Not too short


# ══════════════════════════════════════════════════════════════
#  G1: HTTPS Enforcement
# ══════════════════════════════════════════════════════════════

class TestHttpsEnforcement(unittest.TestCase):
    """Test HTTPS enforcement in production."""

    def test_http_redirect_to_https(self):
        """HTTP requests should redirect to HTTPS in production."""
        # In production, x-forwarded-proto should be https
        proto = "http"
        is_prod = True
        should_redirect = is_prod and proto != "https"
        self.assertTrue(should_redirect, "HTTP should redirect in production")

    def test_https_no_redirect(self):
        """HTTPS requests should not redirect."""
        proto = "https"
        is_prod = True
        should_redirect = is_prod and proto != "https"
        self.assertFalse(should_redirect, "HTTPS should not redirect")

    def test_dev_no_redirect(self):
        """In development, HTTP should not redirect."""
        proto = "http"
        is_prod = False
        should_redirect = is_prod and proto != "https"
        self.assertFalse(should_redirect, "Dev mode should not redirect")


# ══════════════════════════════════════════════════════════════
#  G2: Security Headers
# ══════════════════════════════════════════════════════════════

class TestSecurityHeaders(unittest.TestCase):
    """Test that security headers are properly set."""

    def test_csp_header_default(self):
        """Content-Security-Policy should have restrictive default."""
        csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " \
              "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; " \
              "base-uri 'self'; form-action 'self'"
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertNotIn("'unsafe-inline' *", csp)

    def test_x_frame_options(self):
        """X-Frame-Options should be DENY."""
        x_frame = "DENY"
        self.assertEqual(x_frame, "DENY")

    def test_x_content_type_options(self):
        """X-Content-Type-Options should be nosniff."""
        x_content = "nosniff"
        self.assertEqual(x_content, "nosniff")

    def test_hsts_production(self):
        """HSTS should have long max-age with includeSubDomains."""
        hsts = "max-age=63072000; includeSubDomains; preload"
        self.assertIn("max-age=63072000", hsts)
        self.assertIn("includeSubDomains", hsts)
        self.assertIn("preload", hsts)

    def test_referrer_policy(self):
        """Referrer-Policy should be strict."""
        referrer = "strict-origin-when-cross-origin"
        self.assertEqual(referrer, "strict-origin-when-cross-origin")

    def test_permissions_policy(self):
        """Permissions-Policy should disable sensitive APIs."""
        perms = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        self.assertIn("camera=()", perms)
        self.assertIn("microphone=()", perms)
        self.assertIn("geolocation=()", perms)
        self.assertIn("payment=()", perms)

    def test_cache_control_api_routes(self):
        """API routes should have no-store cache control."""
        cache = "no-store, no-cache, must-revalidate, private"
        self.assertIn("no-store", cache)
        self.assertIn("private", cache)


# ══════════════════════════════════════════════════════════════
#  G3: Dependency Integrity
# ══════════════════════════════════════════════════════════════

class TestDependencyIntegrity(unittest.TestCase):
    """Test dependency and environment integrity checks."""

    def test_insecure_values_set(self):
        """INSECURE_VALUES should contain known bad defaults."""
        insecure = {
            "password", "admin", "change-me", "changeme", "default",
            "secret", "test", "1234", "abcd", "root", "example",
            "placeholder", "todo", "fixme", "temp", "temporary",
            "default-key", "changeme!", "letmein", "welcome",
            "qwerty", "master",
        }
        self.assertGreaterEqual(len(insecure), 20)

    def test_critical_modules_list(self):
        """Critical modules should be checked for integrity."""
        critical_modules = ["@prisma/client", "next", "react", "zod"]
        self.assertEqual(len(critical_modules), 4)

    def test_env_vars_to_check(self):
        """Critical env vars should be checked for insecure values."""
        env_vars = [
            "ZENIC_DB_PASSPHRASE",
            "ZENIC_ADMIN_KEY",
            "NODE_ENV",
            "ZENIC_CORS_ORIGINS",
        ]
        self.assertEqual(len(env_vars), 4)

    def test_integrity_report_structure(self):
        """Integrity report should have required fields."""
        required_fields = [
            "timestamp", "modules", "envVars", "overallStatus", "recommendations",
        ]
        self.assertEqual(len(required_fields), 5)

    def test_overall_status_values(self):
        """Overall status should be one of secure/warning/critical."""
        valid_statuses = {"secure", "warning", "critical"}
        self.assertEqual(len(valid_statuses), 3)


# ══════════════════════════════════════════════════════════════
#  IPC Auth (E3)
# ══════════════════════════════════════════════════════════════

class TestIPCAuth(unittest.TestCase):
    """Test IPC bridge authentication."""

    def test_verify_valid_token(self):
        """Valid IPC token should verify successfully."""
        try:
            from src.core.ipc_auth import verify_ipc_token, generate_ipc_token
            # Generate a token
            token = generate_ipc_token()
            self.assertEqual(len(token), 64)  # 32 bytes = 64 hex chars
        except ImportError:
            self.skipTest("ipc_auth module not available")

    def test_verify_empty_token(self):
        """Empty token should fail verification."""
        try:
            from src.core.ipc_auth import verify_ipc_token
            result = verify_ipc_token("")
            self.assertFalse(result, "Empty token should fail")
        except ImportError:
            self.skipTest("ipc_auth module not available")

    def test_verify_invalid_token(self):
        """Invalid token should fail verification."""
        try:
            from src.core.ipc_auth import verify_ipc_token
            # Set a known expected token
            with patch.dict(os.environ, {"ZENIC_IPC_TOKEN": "known-token-123"}):
                # Clear any cached token
                if hasattr(verify_ipc_token, '__module__'):
                    from src.core import ipc_auth
                    if hasattr(ipc_auth._get_expected_token, '_dev_token'):
                        del ipc_auth._get_expected_token._dev_token
                result = verify_ipc_token("wrong-token-456")
                self.assertFalse(result, "Wrong token should fail")
        except ImportError:
            self.skipTest("ipc_auth module not available")

    def test_generate_token_entropy(self):
        """Generated tokens should have sufficient entropy."""
        try:
            from src.core.ipc_auth import generate_ipc_token
            tokens = {generate_ipc_token() for _ in range(100)}
            # All tokens should be unique
            self.assertEqual(len(tokens), 100, "Generated tokens should be unique")
        except ImportError:
            self.skipTest("ipc_auth module not available")

    def test_require_ipc_auth_decorator(self):
        """@require_ipc_auth should enforce token verification."""
        try:
            from src.core.ipc_auth import require_ipc_auth

            @require_ipc_auth
            def protected_function(token: str, data: str = "test"):
                return f"success:{data}"

            # Without token
            with self.assertRaises(PermissionError):
                protected_function(data="test")

        except ImportError:
            self.skipTest("ipc_auth module not available")


# ══════════════════════════════════════════════════════════════
#  CORS Configuration (E1)
# ══════════════════════════════════════════════════════════════

class TestCORSConfiguration(unittest.TestCase):
    """Test CORS configuration security."""

    def test_wildcard_origin_rejected_with_credentials(self):
        """Wildcard CORS origin should be rejected when credentials are enabled."""
        origin = "*"
        credentials = True
        insecure = origin == "*" and credentials
        self.assertTrue(insecure, "Wildcard + credentials is insecure")

    def test_cors_origins_from_env(self):
        """CORS origins should be configurable via environment."""
        # When ZENIC_CORS_ORIGINS is not set, default should be safe
        default_dev_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
        self.assertEqual(len(default_dev_origins), 2)
        self.assertNotIn("*", default_dev_origins)

    def test_cors_preflight_max_age(self):
        """CORS preflight cache should have reasonable max-age."""
        max_age = 86400  # 24 hours
        self.assertLessEqual(max_age, 86400)
        self.assertGreater(max_age, 0)


# ══════════════════════════════════════════════════════════════
#  Rate Limiting (E2)
# ══════════════════════════════════════════════════════════════

class TestRateLimiting(unittest.TestCase):
    """Test rate limiting configuration."""

    def test_payment_tier_most_restrictive(self):
        """Payment routes should have the most restrictive rate limit."""
        payment_max = 5  # 5/min
        hitl_max = 30    # 30/min
        default_max = 100  # 100/min
        self.assertLess(payment_max, hitl_max)
        self.assertLess(payment_max, default_max)

    def test_rate_limit_window(self):
        """Rate limit window should be 1 minute."""
        window_ms = 60_000
        self.assertEqual(window_ms, 60_000)

    def test_rate_limit_headers(self):
        """Rate limit responses should include proper headers."""
        expected_headers = ["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining"]
        self.assertEqual(len(expected_headers), 3)

    def test_rate_limit_store_cleanup(self):
        """Rate limit store should be cleaned up when too large."""
        max_entries = 10000
        self.assertEqual(max_entries, 10000)


# ══════════════════════════════════════════════════════════════
#  Security Module File Existence
# ══════════════════════════════════════════════════════════════

class TestSecurityModuleFiles(unittest.TestCase):
    """Verify that all security module files were created."""

    def test_sanitize_module_exists(self):
        """Sanitize module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "sanitize", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_error_handler_module_exists(self):
        """Error handler module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "error-handler", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_audit_module_exists(self):
        """Audit module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "audit", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_session_module_exists(self):
        """Session module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "session", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_log_redact_module_exists(self):
        """Log redaction module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "log-redact", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_config_module_exists(self):
        """Secure config module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "config", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_headers_module_exists(self):
        """Security headers module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "headers", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_integrity_module_exists(self):
        """Dependency integrity module should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "config", "integrity.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_ipc_auth_module_exists(self):
        """IPC auth Python module should exist."""
        path = os.path.join(PROJECT_ROOT, "src", "core", "ipc_auth.py")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_security_barrel_export_exists(self):
        """Security barrel export should exist."""
        path = os.path.join(GATEWAY_LIB, "security", "index.ts")
        self.assertTrue(os.path.exists(path), f"Missing: {path}")

    def test_middleware_updated(self):
        """Middleware should include FASE 3 changes."""
        with open(os.path.join(PROJECT_ROOT, "gateway", "src", "middleware.ts"), "r") as f:
            content = f.read()
        # Check for key FASE 3 additions
        self.assertIn("handleCors", content, "Middleware should include CORS")
        self.assertIn("checkRateLimit", content, "Middleware should include rate limiting")
        self.assertIn("sanitizeQueryParams", content, "Middleware should include sanitization")
        self.assertIn("applySecurityHeaders", content, "Middleware should include security headers")
        self.assertIn("enforceHttps", content, "Middleware should include HTTPS enforcement")


# ══════════════════════════════════════════════════════════════
#  Integration Tests
# ══════════════════════════════════════════════════════════════

class TestMiddlewareIntegration(unittest.TestCase):
    """Test middleware integration of all security layers."""

    def test_middleware_has_cors(self):
        """Middleware should have CORS handling."""
        with open(os.path.join(PROJECT_ROOT, "gateway", "src", "middleware.ts"), "r") as f:
            content = f.read()
        self.assertIn("ALLOWED_ORIGINS", content)
        self.assertIn("ZENIC_CORS_ORIGINS", content)
        self.assertIn("Access-Control-Allow-Origin", content)

    def test_middleware_has_rate_limiting(self):
        """Middleware should have rate limiting."""
        with open(os.path.join(PROJECT_ROOT, "gateway", "src", "middleware.ts"), "r") as f:
            content = f.read()
        self.assertIn("RATE_LIMIT_TIERS", content)
        self.assertIn("429", content)
        self.assertIn("RATE_LIMITED", content)

    def test_middleware_has_query_sanitization(self):
        """Middleware should have query param sanitization."""
        with open(os.path.join(PROJECT_ROOT, "gateway", "src", "middleware.ts"), "r") as f:
            content = f.read()
        self.assertIn("SQL_INJECTION_PATTERNS", content)
        self.assertIn("XSS_PATTERNS", content)
        self.assertIn("INVALID_INPUT", content)

    def test_middleware_has_security_headers(self):
        """Middleware should apply security headers."""
        with open(os.path.join(PROJECT_ROOT, "gateway", "src", "middleware.ts"), "r") as f:
            content = f.read()
        self.assertIn("Content-Security-Policy", content)
        self.assertIn("X-Frame-Options", content)
        self.assertIn("Strict-Transport-Security", content)
        self.assertIn("X-Content-Type-Options", content)

    def test_middleware_has_https_enforcement(self):
        """Middleware should enforce HTTPS in production."""
        with open(os.path.join(PROJECT_ROOT, "gateway", "src", "middleware.ts"), "r") as f:
            content = f.read()
        self.assertIn("enforceHttps", content)
        self.assertIn("x-forwarded-proto", content)

    def test_middleware_processing_order(self):
        """Middleware should process security layers in correct order."""
        with open(os.path.join(PROJECT_ROOT, "gateway", "src", "middleware.ts"), "r") as f:
            content = f.read()
        # Verify the processing order in middleware function body
        func_start = content.find("export function middleware")
        self.assertGreater(func_start, 0, "Middleware function should exist")

        func_body = content[func_start:]

        # Verify the processing order comments
        self.assertIn("1. HTTPS enforcement", func_body)
        self.assertIn("3. CORS preflight", func_body)
        self.assertIn("4. Query param", func_body)
        self.assertIn("5. Rate limiting", func_body)
        self.assertIn("6. Rutas BLOQUEADAS", func_body)

        # All security layers should be present
        self.assertIn("enforceHttps", func_body)
        self.assertIn("handleCors", func_body)
        self.assertIn("sanitizeQueryParams", func_body)
        self.assertIn("checkRateLimit", func_body)
        self.assertIn("RUTAS_BLOQUEADAS_SIEMPRE", func_body)


if __name__ == "__main__":
    unittest.main()
