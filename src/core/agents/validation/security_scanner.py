"""
A23 SecurityScanner — SINGLE RESPONSIBILITY: Scan for dangerous patterns.

Deterministic regex scanning. No AI.
INVARIANT: If SecurityScanner says NO (safe=False), it is NO. No override possible.
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import SecurityResult, ValidationIssue

# ──────────────────────────────────────────────────────────────
# DANGEROUS PATTERNS — If detected, safe=False, risk_score increases
# ──────────────────────────────────────────────────────────────

DANGEROUS_PATTERNS: list[tuple] = [
    ("dangerous_eval", r'\beval\s*\(', "eval() is dangerous — use ast.literal_eval()"),
    ("dangerous_exec", r'\bexec\s*\(', "exec() is dangerous — avoid dynamic code execution"),
    ("os_system", r'\bos\.system\s*\(', "os.system() is dangerous — use subprocess with shell=False"),
    ("pickle_load", r'\bpickle\.loads?\s*\(', "pickle is dangerous — use json or msgpack"),
    ("yaml_unsafe", r'\byaml\.load\s*\([^)]*(?!Loader)', "yaml.load() without Loader is unsafe — use yaml.safe_load()"),
    ("sql_injection", r'f["\'].*SELECT.*\{.*\}', "Possible SQL injection via f-string"),
    ("subprocess_shell", r'\bsubprocess\.\w+\s*\(.*shell\s*=\s*True', "subprocess with shell=True is dangerous"),
    ("weak_hash_md5", r'\bhashlib\.md5\s*\(', "MD5 is cryptographically broken — use sha256"),
    ("weak_hash_sha1", r'\bhashlib\.sha1\s*\(', "SHA1 is cryptographically weak — use sha256"),
    ("assert_in_prod", r'\bassert\s+', "assert statements are stripped in optimized mode"),
    ("bare_except", r'\bexcept\s*:', "Bare except catches all exceptions including SystemExit"),
    ("broad_exception", r'\bexcept\s+Exception\s*:', "Broad exception catching — be more specific"),
    ("input_injection", r'\binput\s*\(', "input() can be a vector for injection in production"),
]

# ──────────────────────────────────────────────────────────────
# SAFE PATTERNS — Evidence that code is well-written
# ──────────────────────────────────────────────────────────────

SAFE_PATTERNS: list[tuple] = [
    ("error_handling", r'\btry\s*:', "Proper error handling"),
    ("type_hints", r'def\s+\w+\s*\([^)]*:\s*\w+', "Type hints present"),
    ("logging", r'\blogging\b|\blogger\b', "Logging present"),
    ("context_manager", r'\bwith\s+open', "Context manager for file handling"),
    ("validation", r'\bif\s+not\s+\w+\s*:', "Input validation present"),
    ("safe_deserialize", r'\bjson\.loads?\s*\(', "Safe JSON deserialization"),
]


class SecurityScanner(BaseAgent[SecurityResult]):
    """
    A23: Scan code for dangerous patterns.

    Single Responsibility: Security scanning ONLY.
    Method: Regex pattern matching (deterministic).
    Fallback: Return safe=True (trust by default when no code to scan).

    INVARIANT: If safe=False, it CANNOT be overridden. Security veto is absolute.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A23_SecurityScanner", **kwargs)
        self._dangerous_compiled = [
            (name, re.compile(pattern, re.IGNORECASE), msg)
            for name, pattern, msg in DANGEROUS_PATTERNS
        ]
        self._safe_compiled = [
            (name, re.compile(pattern, re.IGNORECASE), msg)
            for name, pattern, msg in SAFE_PATTERNS
        ]

    def execute(self, input_data: Any) -> SecurityResult:
        """
        Scan code for security threats.

        input_data should be a dict with:
          - 'code': str — the code to scan
          - 'language': str (optional)
        """
        code = ""
        if isinstance(input_data, dict):
            code = input_data.get("code", "")
        elif isinstance(input_data, str):
            code = input_data

        if not code:
            return SecurityResult(safe=True, source="deterministic")

        threats = self._scan_dangerous(code)
        safe_evidence = self._scan_safe(code)

        # Calculate risk score
        risk_score = self._calculate_risk(threats, safe_evidence)

        # safe=False if ANY dangerous pattern found
        safe = len(threats) == 0

        return SecurityResult(
            safe=safe,
            threats=threats,
            risk_score=round(risk_score, 2),
            source="deterministic",
        )

    def _scan_dangerous(self, code: str) -> list[ValidationIssue]:
        """Scan for dangerous patterns."""
        threats = []
        for name, pattern, message in self._dangerous_compiled:
            matches = pattern.findall(code)
            if matches:
                # Find line number
                for match in pattern.finditer(code):
                    line_num = code[:match.start()].count('\n') + 1
                    threats.append(ValidationIssue(
                        severity="error",
                        code=name,
                        message=message,
                        line=line_num,
                        suggestion=self._get_suggestion(name),
                    ))
                    break  # Only report first occurrence
        return threats

    def _scan_safe(self, code: str) -> list[ValidationIssue]:
        """Scan for safe patterns (evidence of good practices)."""
        evidence = []
        for name, pattern, message in self._safe_compiled:
            if pattern.search(code):
                evidence.append(ValidationIssue(
                    severity="info",
                    code=name,
                    message=message,
                ))
        return evidence

    def _calculate_risk(self, threats: list, safe_evidence: list) -> float:
        """Calculate risk score from threats and safe patterns."""
        if not threats:
            return 0.0

        # Each threat adds weight
        threat_weight = sum(
            0.3 if t.severity == "error" else 0.1
            for t in threats
        )

        # Safe patterns reduce risk
        safe_reduction = len(safe_evidence) * 0.05

        return max(0.0, min(threat_weight - safe_reduction, 1.0))

    @staticmethod
    def _get_suggestion(code: str) -> str:
        """Get fix suggestion for a vulnerability code."""
        SUGGESTIONS = {
            "dangerous_eval": "Replace eval() with ast.literal_eval() for safe evaluation",
            "dangerous_exec": "Remove exec() — use function dispatch or import instead",
            "os_system": "Replace os.system() with subprocess.run(shell=False)",
            "pickle_load": "Replace pickle with json.loads() or msgpack for safe deserialization",
            "yaml_unsafe": "Replace yaml.load() with yaml.safe_load()",
            "sql_injection": "Use parameterized queries instead of f-string SQL",
            "subprocess_shell": "Set shell=False and pass arguments as a list",
            "weak_hash_md5": "Replace hashlib.md5() with hashlib.sha256()",
            "weak_hash_sha1": "Replace hashlib.sha1() with hashlib.sha256()",
            "assert_in_prod": "Replace assert with proper if/raise validation",
            "bare_except": "Replace bare except with specific exception types",
            "broad_exception": "Catch specific exceptions instead of Exception",
            "input_injection": "Validate and sanitize all input() values",
        }
        return SUGGESTIONS.get(code, "Review and fix this security issue")

    def fallback(self, input_data: Any) -> SecurityResult:
        """
        Fallback: Return safe=False with moderate risk (precaution principle).

        When the scanner is degraded (circuit open, errors), we cannot guarantee
        safety, so safe=False (veto applies). However, we use risk_score=0.5
        (not 1.0) to avoid total pipeline lockout — downstream components can
        differentiate between "scanner found real threats" (high risk_score)
        and "scanner was unavailable" (moderate risk_score from fallback).

        The source="fallback" field allows the pipeline to identify this as
        a degraded result rather than an actively malicious one.
        """
        return SecurityResult(
            safe=False,
            risk_score=0.5,
            source="fallback",
            threats=[ValidationIssue(
                severity="warning",
                code="scanner_degraded",
                message="Security scanner unavailable — cannot verify code safety",
            )],
        )
