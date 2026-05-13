"""
CodeAgent Helpers — static / utility methods and shared constants.

Extracted from the monolithic code_agent.py (1,043 lines) as part of the
mixin-based modularisation.  Every method here is a pure helper that does
not depend on CodeAgent instance state beyond what is passed explicitly.
"""

import re
from typing import Any, Dict, List, Optional

from src.core.agents.schemas import CodeOutput, FileSpec
from src.core.agents.prompts import AgentPrompts

# Language → default file extension
LANG_EXTENSIONS = {
    "python": ".py", "kotlin": ".kt", "go": ".go",
    "javascript": ".js", "typescript": ".ts", "java": ".java",
}

# Task type → system prompt mapping
TASK_PROMPTS = {
    "generate": AgentPrompts.CODE_SYSTEM_GENERATE,
    "transform": AgentPrompts.CODE_SYSTEM_TRANSFORM,
    "scaffold": AgentPrompts.CODE_SYSTEM_SCAFFOLD,
    "optimize": AgentPrompts.CODE_SYSTEM_TRANSFORM,
    "fix": AgentPrompts.CODE_SYSTEM_TRANSFORM,
}


class CodeAgentHelpersMixin:
    """Mixin with static / helper methods for CodeAgent."""

    # ============================================================
    #  COMPATIBILITY: CodeGenerator methods preserved
    # ============================================================

    @staticmethod
    def extract_solver_insights(solver_proof) -> Dict[str, Any]:
        """Extract code generation insights from solver results.

        Preserves CodeGenerator.extract_solver_insights() contract.
        """
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
    def extract_ast_context(ast_analysis) -> Dict[str, Any]:
        """Extract detailed context from AST analysis. Preserves CodeGenerator contract."""
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

    # ============================================================
    #  PRIVATE HELPERS
    # ============================================================

    def _safe_name(self, text: str) -> str:
        """Convierte texto en nombre de módulo seguro."""
        name = re.sub(r'[^\w]', '_', text.lower().strip())
        name = re.sub(r'_+', '_', name).strip('_')
        # Remove common stop words
        stop = {'un', 'una', 'el', 'la', 'los', 'las', 'a', 'de', 'del',
                'en', 'por', 'para', 'con', 'that', 'the', 'a', 'an',
                'create', 'make', 'generate', 'build', 'write'}
        parts = [p for p in name.split('_') if p and p not in stop]
        return '_'.join(parts[:4]) if parts else "module"

    def _json_to_code_output(self, data: Dict[str, Any],
                             source: str = "llm") -> Optional[CodeOutput]:
        """Convierte dict JSON a CodeOutput."""
        code = str(data.get("code", "")).strip()
        language = str(data.get("language", "python")).strip()

        # If no code field, try to find it in files
        if not code:
            files_raw = data.get("files", [])
            if isinstance(files_raw, list) and files_raw:
                first = files_raw[0] if isinstance(files_raw[0], dict) else {}
                code = str(first.get("content", "")).strip()
                if not language or language == "python":
                    language = str(first.get("language", language)).strip()

        if not code:
            return None

        # Parse files
        files = []
        for f in data.get("files", []):
            if isinstance(f, dict):
                files.append(FileSpec(
                    path=str(f.get("path", "")),
                    content=str(f.get("content", "")),
                    language=str(f.get("language", language)),
                ))

        explanation = str(data.get("explanation", ""))

        test_code = str(data.get("test_code", ""))

        return CodeOutput(
            code=code,
            language=language,
            files=files,
            test_code=test_code,
            explanation=explanation,
            source=source,
        )

    def _parse_code_blocks(self, text: str,
                           source: str = "llm") -> Optional[CodeOutput]:
        """Extrae código de bloques markdown en texto libre del LLM."""
        # Find code blocks
        code_blocks = re.findall(
            r'```(\w+)?\s*\n(.*?)\n```', text, re.DOTALL
        )

        if not code_blocks:
            # No code blocks found - return None to trigger fallback
            return None

        # Use first code block as main code
        lang = code_blocks[0][0] or "python"
        code = code_blocks[0][1].strip()

        # Additional blocks as files
        files = []
        for i, (block_lang, block_code) in enumerate(code_blocks[1:], 1):
            ext = LANG_EXTENSIONS.get(block_lang or lang, ".txt")
            files.append(FileSpec(
                path=f"file_{i}{ext}",
                content=block_code.strip(),
                language=block_lang or lang,
            ))

        return CodeOutput(
            code=code,
            language=lang,
            files=files,
            explanation=text[:200],
            source=source,
        )
