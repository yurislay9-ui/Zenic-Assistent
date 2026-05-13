"""
ValidationAgent private helper methods mixin.
"""

import logging
from typing import Any, Dict, List, Optional

from ._imports import (
    ValidationOutput, ValidationIssue,
    logger,
)


class HelpersMixin:
    """Private helper methods for ValidationAgent."""

    # ============================================================
    #  PRIVATE HELPERS
    # ============================================================

    def _get_block_category(self, block: Any) -> str:
        """Obtiene la categoría de un bloque."""
        if isinstance(block, dict):
            return block.get("category", block.get("type", "unknown"))
        return getattr(block, 'category', getattr(block, 'name', 'unknown'))

    def _calculate_risk_score(self, issues: List[ValidationIssue]) -> float:
        """Calcula risk score basado en issues encontrados."""
        if not issues:
            return 0.0

        weights = {"error": 0.3, "warning": 0.1, "info": 0.02}
        score = sum(weights.get(i.severity, 0.02) for i in issues)
        return min(1.0, score)

    def _generate_suggestions(self, issues: List[ValidationIssue]) -> List[str]:
        """Genera sugerencias de los issues encontrados."""
        suggestions = []
        error_types = set()
        for issue in issues:
            if issue.severity == "error" and issue.code not in error_types:
                error_types.add(issue.code)
                if issue.suggestion:
                    suggestions.append(issue.suggestion)

        if not suggestions:
            suggestions.append("No critical issues found")

        return suggestions[:5]

    def _get_fix_suggestion(self, code: str) -> str:
        """Sugerencia de fix para un tipo de issue."""
        fix_map = {
            "dangerous_eval": "Replace eval() with ast.literal_eval() or json.loads()",
            "dangerous_exec": "Avoid exec() - use functions instead",
            "command_injection": "Use subprocess.run() with shell=False",
            "shell_injection": "Use subprocess with shell=False and pass args as list",
            "pickle_deserialization": "Use json or msgpack instead of pickle",
            "yaml_unsafe_load": "Use yaml.safe_load() instead of yaml.load()",
            "weak_hash_md5": "Use hashlib.sha256() or stronger",
            "weak_hash_sha1": "Use hashlib.sha256() or stronger",
            "bare_except": "Use 'except Exception:' instead of bare 'except:'",
            "broad_exception": "Catch more specific exceptions",
            "select_star": "Specify columns explicitly instead of SELECT *",
            "format_injection": "Use f-strings or validate format arguments",
            "unvalidated_input": "Validate and sanitize all user input",
            "resource_leak": "Use 'with' statement for file/resource handling",
            "missing_return": "Add return statement on all code paths",
        }
        return fix_map.get(code, "Review and fix this issue")

    def _json_to_validation_output(self, data: Dict[str, Any],
                                    source: str = "llm") -> Optional[ValidationOutput]:
        """Convierte dict JSON a ValidationOutput."""
        is_valid = data.get("is_valid", True)
        if isinstance(is_valid, str):
            is_valid = is_valid.lower() == "true"

        # Parse issues
        issues = []
        for i_data in data.get("issues", []):
            if isinstance(i_data, dict):
                issues.append(ValidationIssue(
                    severity=str(i_data.get("severity", "warning")),
                    code=str(i_data.get("code", "")),
                    message=str(i_data.get("message", "")),
                    line=int(i_data.get("line", 0)),
                    suggestion=str(i_data.get("suggestion", "")),
                ))

        suggestions = data.get("suggestions", [])
        if isinstance(suggestions, str):
            suggestions = [suggestions]

        risk_score = data.get("risk_score", 0.0)
        try:
            risk_score = float(risk_score)
            risk_score = max(0.0, min(1.0, risk_score))
        except (ValueError, TypeError):
            risk_score = 0.0

        return ValidationOutput(
            is_valid=bool(is_valid),
            issues=issues,
            suggestions=suggestions if isinstance(suggestions, list) else [],
            risk_score=risk_score,
            source=source,
        )

    def _parse_free_text_validation(self, text: str,
                                     source: str = "llm") -> Optional[ValidationOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        if not text or len(text) < 10:
            return None

        # Try to extract issues from text
        issues = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith(('-', '*', '•')):
                issues.append(ValidationIssue(
                    severity="warning",
                    code="llm_detected",
                    message=line.lstrip('-*• '),
                    suggestion="Review this issue",
                ))

        is_valid = len(issues) == 0

        return ValidationOutput(
            is_valid=is_valid,
            issues=issues[:10],
            suggestions=["Review LLM findings"] if issues else ["No issues found"],
            risk_score=0.1 if issues else 0.0,
            source=source,
        )
