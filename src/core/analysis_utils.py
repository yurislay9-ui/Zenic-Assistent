"""
Analysis Utilities - Quality reporting, code explanation, dependency checking, and logging.

Utility methods for analyzing code quality, explaining code, checking dependencies,
and logging requests. Most methods are pure functions or need minimal orchestrator access.
"""

import ast
import json
import uuid
import logging

from src.core.shared.db_initializer import get_connection

logger = logging.getLogger(__name__)


class AnalysisUtils:
    """Analysis and reporting utilities for the orchestrator."""

    def __init__(self, orchestrator=None):
        """
        Initialize with optional reference to the orchestrator.

        Args:
            orchestrator: ZenicOrchestrator instance for accessing pipeline components.
                         Only needed for check_dependencies (which needs ast_engine).
        """
        self._orchestrator = orchestrator

    def apply_fix(self, code, intent, lang):
        if lang == "python" and code:
            # CodeTransformer removed — module deleted; return code as-is
            return code
        return code or ""

    @staticmethod
    def generate_quality_report(analysis, code, lang):
        parts = [
            f"QUALITY REPORT - ZENIC-AGENTS",
            f"Functions: {analysis.get('functions', 0)}",
            f"Classes: {analysis.get('classes', 0)}",
            f"Max complexity: {analysis.get('max_complexity', 0)}",
            f"Avg complexity: {analysis.get('avg_complexity', 0)}",
        ]
        if analysis.get('max_complexity', 0) > 10:
            parts.append("ALERT: Function with complexity >10 detected. Refactor recommended.")
        if analysis.get('total_complexity', 0) > 50:
            parts.append("ALERT: High total complexity. Consider splitting into modules.")
        return "\n".join(parts)

    @staticmethod
    def explain_code(code, lang, ast_analysis):
        parts = ["CODE ANALYSIS - ZENIC-AGENTS"]
        if lang == "python":
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        doc = ast.get_docstring(node) or "No docstring"
                        args = [a.arg for a in node.args.args]
                        parts.append(f"\nFunction: {node.name}")
                        parts.append(f"  Args: {', '.join(args) if args else 'none'}")
                        parts.append(f"  Doc: {doc}")
                    elif isinstance(node, ast.ClassDef):
                        doc = ast.get_docstring(node) or "No docstring"
                        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                        parts.append(f"\nClass: {node.name}")
                        parts.append(f"  Methods: {', '.join(methods) if methods else 'none'}")
                        parts.append(f"  Doc: {doc}")
            except SyntaxError:
                parts.append("Syntax error - cannot analyze AST")
        if ast_analysis:
            parts.append(f"\nMetrics: {ast_analysis.get('functions', 0)} functions, {ast_analysis.get('classes', 0)} classes")
        return "\n".join(parts)

    @staticmethod
    def explain_concept(intent):
        return (f"ZENIC-AGENTS - Explanation\n"
                f"Operation: {intent.op}\nTarget: {intent.target}\n"
                f"Goal: {intent.goal}\nConfidence: {intent.confidence}\n\n"
                f"Include code in your message for detailed analysis.")

    @staticmethod
    def analyze_and_respond(code, intent, ast_analysis):
        parts = [f"ANALYSIS - ZENIC-AGENTS - {intent.op}"]
        if ast_analysis:
            parts.append(f"Complexity: {ast_analysis.get('avg_complexity', 0)} (avg)")
            parts.append(f"Functions: {ast_analysis.get('function_names', [])}")
            parts.append(f"Classes: {ast_analysis.get('class_names', [])}")
        return "\n".join(parts)

    @staticmethod
    def general_response(intent):
        return (f"ZENIC-AGENTS\n"
                f"Op: {intent.op} | Target: {intent.target}\n"
                f"Goal: {intent.goal} | Lang: {intent.language}\n\n"
                f"Include code with ```python ... ``` for full analysis.")

    @staticmethod
    def full_analysis(code, intent, ast_analysis, lang):
        parts = ["FULL ANALYSIS - ZENIC-AGENTS", f"Language: {lang}", f"Operation: {intent.op}"]
        if ast_analysis:
            parts.extend([f"Functions: {ast_analysis.get('functions', 0)}",
                         f"Classes: {ast_analysis.get('classes', 0)}",
                         f"Max complexity: {ast_analysis.get('max_complexity', 0)}",
                         f"Avg complexity: {ast_analysis.get('avg_complexity', 0)}"])
        return "\n".join(parts)

    def check_dependencies(self, code, target, lang):
        if not self._orchestrator:
            return ["No orchestrator available for dependency check"]
        ast_engine = getattr(self._orchestrator, 'ast_engine', None)
        if not ast_engine:
            return ["No AST engine available for dependency check"]
        nodes = ast_engine.get_node_info(target.replace('.py', ''))
        results = []
        if nodes:
            for n in nodes[:5]:
                conns = json.loads(n.get('connections', '[]'))
                results.append(f"  {n['node_type']} '{n['name']}' -> deps: {conns}")
        else:
            results.append(f"  No dependencies found for '{target}'")
        return results

    # ============================================================
    #  LOGGING
    # ============================================================

    @staticmethod
    def log_request(intent, status, elapsed_ms, cache_hit=False,
                    solver_status="", mcts_sims=0):
        if intent is None:
            return
        try:
            conn = get_connection("request_log.sqlite")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO requests
                (request_id, model, operation, goal, route, status,
                 processing_time_ms, solver_status, mcts_simulations, cache_hit)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4())[:8], "zenic-agents",
                 intent.op, intent.goal, "", status, elapsed_ms,
                 solver_status, mcts_sims, int(cache_hit)))
            conn.commit()
        except Exception as e:
            logger.debug(f"AnalysisUtils: Failed to log request to database: {e}")
