"""
Pipeline intelligence extractors for CodeGenerator.
"""

import re
from src.core.shared.contracts import OperationType, GoalType


class ExtractorsMixin:
    """Pipeline intelligence extractors for CodeGenerator."""

    @staticmethod
    def extract_solver_insights(solver_proof):
        """Extract code generation insights from solver results."""
        insights = {
            "null_safety_required": False,
            "type_safety_required": False,
            "critical_target": False,
            "validated_constraints": [],
            "violated_constraints": [],
            "solver_type": "none",
            "status": "none",
        }
        if not solver_proof:
            return insights

        status = solver_proof.get("status", "")
        insights["status"] = status
        insights["solver_type"] = solver_proof.get("solver_type", "none")

        if status == "PROVEN":
            proof_str = solver_proof.get("proof", "")
            insights["validated_constraints"] = [proof_str] if proof_str else []
            proof_lower = proof_str.lower() if proof_str else ""
            if "null" in proof_lower or "none" in proof_lower:
                insights["null_safety_required"] = True
            if "type" in proof_lower:
                insights["type_safety_required"] = True
            if "critical" in proof_lower:
                insights["critical_target"] = True

        elif status in ("VIOLATED", "LIKELY_VIOLATED"):
            cex = solver_proof.get("counterexamples", [])
            insights["violated_constraints"] = cex if isinstance(cex, list) else [str(cex)]
            for ce in insights["violated_constraints"]:
                ce_str = str(ce).lower()
                if "none" in ce_str or "null" in ce_str:
                    insights["null_safety_required"] = True
                if "type" in ce_str:
                    insights["type_safety_required"] = True

        elif status == "SATISFIED":
            assignment = solver_proof.get("assignment", {})
            if isinstance(assignment, dict):
                for key, val in assignment.items():
                    insights["validated_constraints"].append(f"{key}={val}")

        constraints_in_proof = solver_proof.get("constraints", [])
        for c in (constraints_in_proof if isinstance(constraints_in_proof, list) else []):
            desc = str(c).lower() if isinstance(c, str) else str(getattr(c, "description", "")).lower()
            if "critical" in desc:
                insights["critical_target"] = True
            if "null" in desc or "none" in desc:
                insights["null_safety_required"] = True
        return insights

    @staticmethod
    def extract_ast_context(ast_analysis):
        """Extract detailed context from AST analysis for code generation."""
        ctx = {
            "function_signatures": [],
            "class_hierarchies": [],
            "import_dependencies": [],
            "call_relationships": [],
            "existing_patterns": [],
            "function_names": [],
            "class_names": [],
            "max_complexity": 0,
        }
        if not ast_analysis:
            return ctx
        ctx["function_names"] = ast_analysis.get("function_names", [])
        ctx["class_names"] = ast_analysis.get("class_names", [])
        ctx["max_complexity"] = ast_analysis.get("max_complexity", 0)
        for conn in ast_analysis.get("connections", []):
            conn_str = str(conn)
            if "extends:" in conn_str:
                parent = conn_str.replace("extends:", "")
                child = ""
                for cls in ctx["class_names"]:
                    if cls in conn_str or conn_str.startswith(cls):
                        child = cls
                        break
                ctx["class_hierarchies"].append({"child": child, "parent": parent})
            elif "method:" in conn_str:
                parts = conn_str.split("method:")
                ctx["call_relationships"].append({"caller": parts[0], "method": parts[1] if len(parts) > 1 else ""})
            else:
                ctx["import_dependencies"].append(conn_str)
        fn_names = ctx["function_names"]
        if any(n.startswith("get_") for n in fn_names):
            ctx["existing_patterns"].append("getter")
        if any(n.startswith("set_") for n in fn_names):
            ctx["existing_patterns"].append("setter")
        if any(n.startswith("_") for n in fn_names):
            ctx["existing_patterns"].append("private_methods")
        if any(n.startswith("validate_") or n.startswith("check_") for n in fn_names):
            ctx["existing_patterns"].append("validation")
        return ctx

    @staticmethod
    def extract_symbolic_insights(sandbox_result):
        """Extract code generation insights from sandbox symbolic execution results."""
        insights = {
            "symbolic_violations": [],
            "concrete_test_inputs": [],
            "division_by_zero_risks": [],
            "null_dereference_risks": [],
            "index_oob_risks": [],
            "z3_proven_violations": [],
            "paths_explored": 0,
            "paths_pruned": 0,
            "feasible_paths": 0,
            "smt_paths_available": False,
        }
        if not sandbox_result:
            return insights
        warnings = getattr(sandbox_result, 'warnings', [])
        for warning in warnings:
            warning_str = str(warning)
            if "Symbolic (Z3 PROVEN)" in warning_str:
                insights["z3_proven_violations"].append(warning_str)
                if "division by zero" in warning_str.lower():
                    insights["division_by_zero_risks"].append(warning_str)
                elif "none dereference" in warning_str.lower():
                    insights["null_dereference_risks"].append(warning_str)
                elif "index out of bounds" in warning_str.lower():
                    insights["index_oob_risks"].append(warning_str)
            elif "Symbolic:" in warning_str:
                insights["symbolic_violations"].append(warning_str)
        metrics = getattr(sandbox_result, 'metrics', {})
        if isinstance(metrics, dict):
            insights["paths_explored"] = metrics.get("paths_explored", 0)
            insights["paths_pruned"] = metrics.get("paths_pruned", 0)
            insights["feasible_paths"] = metrics.get("feasible_paths", 0)
            insights["smt_paths_available"] = metrics.get("smt_paths_available", False)
            test_inputs = metrics.get("test_inputs_sample", [])
            if isinstance(test_inputs, list):
                insights["concrete_test_inputs"] = test_inputs
        return insights
