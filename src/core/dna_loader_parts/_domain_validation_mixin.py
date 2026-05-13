"""
Domain expert rules and validation gates API mixin for DNALoader.
"""

import re
import ast
import logging
from typing import Dict, Any, List, Optional

from ._imports import logger, DomainRule, ValidationGate


class DomainValidationMixin:
    """Mixin with domain expert rules and validation gates API methods."""

    # ================================================================
    #  DOMAIN EXPERT RULES API
    # ================================================================

    def get_domain_rules(self, industry: str) -> Optional[DomainRule]:
        """Obtiene las reglas de negocio para una industria."""
        if not self._loaded:
            self.load_all()
        return self._domain_rules.get(industry)

    def get_mandatory_logic(self, industry: str) -> List[str]:
        """Obtiene las reglas obligatorias de una industria."""
        rules = self.get_domain_rules(industry)
        return rules.mandatory_logic if rules else []

    def find_industry_for_niche(self, niche_domain: str) -> Optional[DomainRule]:
        """Encuentra las reglas de industria más cercanas para un dominio de nicho."""
        if not self._loaded:
            self.load_all()

        # Direct match
        if niche_domain in self._domain_rules:
            return self._domain_rules[niche_domain]

        # Partial match
        domain_lower = niche_domain.lower()
        for name, rule in self._domain_rules.items():
            if domain_lower in name or name in domain_lower:
                return rule

        return None

    # ================================================================
    #  VALIDATION GATES API
    # ================================================================

    def get_global_gates(self, category: str = "") -> List[ValidationGate]:
        """Obtiene gates de validación globales, filtradas por categoría."""
        if not self._loaded:
            self.load_all()
        if category:
            return [g for g in self._validation_gates
                    if g.category == category and g.category != "domain_specific"]
        return [g for g in self._validation_gates if g.category != "domain_specific"]

    def get_domain_gates(self, domain: str) -> List[ValidationGate]:
        """Obtiene gates de validación específicas de un dominio."""
        if not self._loaded:
            self.load_all()
        return self._domain_gates.get(domain, [])

    def validate_code(self, code: str, domain: str = "") -> Dict[str, Any]:
        """
        Valida código contra todas las gates aplicables.

        Returns:
            Dict with passed, failed, warnings, and auto_fixes
        """
        if not self._loaded:
            self.load_all()

        results = {
            "passed": [],
            "failed": [],
            "warnings": [],
            "auto_fixes": [],
            "score": 0.0,
        }

        all_gates = list(self.get_global_gates())
        if domain:
            all_gates.extend(self.get_domain_gates(domain))

        for gate in all_gates:
            check_result = self._check_gate(code, gate)
            if check_result == "pass":
                results["passed"].append(gate.id)
            elif check_result == "fail":
                if gate.severity == "critical":
                    results["failed"].append({
                        "id": gate.id,
                        "rule": gate.rule,
                        "auto_fix": gate.auto_fix,
                        "fix_strategy": gate.fix_strategy if gate.auto_fix else "",
                    })
                else:
                    results["warnings"].append({
                        "id": gate.id,
                        "rule": gate.rule,
                    })

        # Calculate score
        total = len(all_gates)
        passed = len(results["passed"])
        results["score"] = round(passed / max(total, 1) * 100, 1)

        return results

    def _check_gate(self, code: str, gate: ValidationGate) -> str:
        """Ejecuta una validación individual contra el código."""
        # Pattern-based checks
        if gate.pattern:
            try:
                if re.search(gate.pattern, code, re.MULTILINE):
                    return "fail" if gate.id.startswith("no_") else "pass"
                return "pass" if gate.id.startswith("no_") else "fail"
            except re.error:
                pass

        # Action-based checks
        action = gate.action.lower()
        code_lower = code.lower()

        if action == "regex_search_keys":
            secret_patterns = [
                r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
                r'(?:AWS_SECRET|PRIVATE_KEY)\s*=\s*["\'][^"\']+["\']',
            ]
            for pat in secret_patterns:
                if re.search(pat, code, re.IGNORECASE):
                    return "fail"
            return "pass"

        elif action == "ast_tree_check":
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if gate.id == "all_async_in_try_except":
                            if isinstance(node, ast.AsyncFunctionDef):
                                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                                if not has_try:
                                    return "fail"
                        elif gate.id == "every_function_must_have_docstring":
                            doc = ast.get_docstring(node)
                            if not doc:
                                return "fail"
                return "pass"
            except SyntaxError:
                return "fail"

        elif action == "lint_check":
            # Simple lint checks
            if gate.id == "every_function_must_have_docstring":
                try:
                    tree = ast.parse(code)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not ast.get_docstring(node):
                                return "fail"
                    return "pass"
                except SyntaxError:
                    return "fail"
            return "pass"

        elif "sql" in action.lower() or "injection" in gate.id:
            sql_patterns = [
                r'f["\'].*SELECT.*{.*}.*["\']',
                r'f["\'].*INSERT.*{.*}.*["\']',
                r'\+\s*["\']SELECT',
                r'\+\s*["\']INSERT',
            ]
            for pat in sql_patterns:
                if re.search(pat, code, re.IGNORECASE):
                    return "fail"
            return "pass"

        elif "eval" in gate.id:
            if "eval(" in code or "exec(" in code:
                return "fail"
            return "pass"

        elif "bare" in gate.id:
            if re.search(r'except\s*:', code):
                return "fail"
            return "pass"

        elif "https" in gate.id:
            if re.search(r'http://(?!localhost|127\.0\.0\.1)', code):
                return "fail"
            return "pass"

        elif "docstring" in gate.id:
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not ast.get_docstring(node):
                            return "fail"
                return "pass"
            except SyntaxError:
                return "pass"

        # Default: pass (can't auto-check this rule)
        return "pass"
