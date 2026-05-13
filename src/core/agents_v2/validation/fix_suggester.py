"""
A28 FixSuggester — SINGLE RESPONSIBILITY: Suggest fixes for validation issues.

Deterministic. No AI.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import FixSuggestions, ValidationIssue

# Fix suggestion catalog
FIX_CATALOG: dict[str, str] = {
    "dangerous_eval": "Replace eval() with ast.literal_eval() for safe evaluation",
    "dangerous_exec": "Remove exec() and use function dispatch or importlib instead",
    "os_system": "Replace os.system() with subprocess.run(shell=False, check=True)",
    "pickle_load": "Replace pickle with json.loads() or msgpack for safe deserialization",
    "yaml_unsafe": "Replace yaml.load() with yaml.safe_load()",
    "sql_injection": "Use parameterized queries: cursor.execute('SELECT ? WHERE id=?', (val,))",
    "subprocess_shell": "Set shell=False and pass command as a list of arguments",
    "weak_hash_md5": "Replace hashlib.md5() with hashlib.sha256() for cryptographic security",
    "weak_hash_sha1": "Replace hashlib.sha1() with hashlib.sha256() for cryptographic security",
    "assert_in_prod": "Replace assert with proper if/raise ValueError validation",
    "bare_except": "Replace bare except with specific exception types (ValueError, IOError, etc.)",
    "broad_exception": "Catch specific exceptions instead of generic Exception",
    "input_injection": "Validate and sanitize all input values with type checks and bounds",
    "missing_return": "Ensure all code paths in the function return a value",
    "resource_leak": "Use 'with open(...) as f:' context manager for file operations",
    "syntax_error": "Fix the syntax error as indicated by the parser",
    "unmatched_brace": "Add missing closing brace/bracket/parenthesis",
    "mismatched_brace": "Match opening and closing braces correctly",
    "unclosed_brace": "Add closing brace/bracket/parenthesis for the unclosed symbol",
}

# Auto-fixable codes (can be fixed mechanically)
AUTO_FIXABLE = {
    "bare_except", "yaml_unsafe",
}


class FixSuggester(BaseAgent[FixSuggestions]):
    """
    A28: Suggest fixes for validation issues.

    Single Responsibility: Fix suggestion ONLY.
    Method: Catalog lookup (deterministic).
    Fallback: Return empty suggestions.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A28_FixSuggester", **kwargs)

    def execute(self, input_data: Any) -> FixSuggestions:
        """
        Generate fix suggestions for validation issues.

        input_data should be a list of ValidationIssue objects,
        or a dict with 'issues' key.
        """
        issues: list[ValidationIssue] = []

        if isinstance(input_data, list):
            issues = input_data
        elif isinstance(input_data, dict):
            issues = input_data.get("issues", [])

        if not issues:
            return FixSuggestions(source="deterministic")

        suggestions = []
        priorities = []
        auto_fixable = []

        for issue in issues:
            if not isinstance(issue, ValidationIssue):
                continue

            suggestion = FIX_CATALOG.get(issue.code, f"Review and fix: {issue.message}")
            suggestions.append(suggestion)

            # Priority based on severity
            if issue.severity == "error":
                priorities.append("high")
            elif issue.severity == "warning":
                priorities.append("medium")
            else:
                priorities.append("low")

            # Check if auto-fixable
            if issue.code in AUTO_FIXABLE:
                auto_fixable.append(issue.code)

        return FixSuggestions(
            suggestions=suggestions,
            priorities=priorities,
            auto_fixable=auto_fixable,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> FixSuggestions:
        return FixSuggestions(source="fallback")
