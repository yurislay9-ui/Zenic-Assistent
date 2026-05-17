"""
Pipeline-driven code generation for CodeGenerator.

M1 FIX: When generating feature modules, the _process() method now uses
CodeAssembler to produce REAL CRUD/analytics/notification logic instead
of the stub: return {"processed": True, "input": payload}
"""

import re
import logging
from src.core.shared.contracts import OperationType, GoalType

from ._process_builder import ProcessBuilderMixin
logger = logging.getLogger("core.code_gen_parts._pipeline_mixin._core")


class PipelineMixin(ProcessBuilderMixin):
    """Pipeline-driven code generation for CodeGenerator."""

    def generate_pipeline_driven_code(self, intent, ast_analysis, plan, lang):
        """Generate code using ALL pipeline data: AST + Solver + MCTS."""
        solver_insights = self.extract_solver_insights(plan.solver_proof if plan else None)
        mcts_actions = [s.action for s in plan.steps] if plan else []
        ast_context = self.extract_ast_context(ast_analysis)

        target = intent.target
        safe_target = re.sub(r'[^\w]', '_', target.replace('.py', '').replace('.kt', '').replace('.go', '').replace('.js', '')) if target != "unknown" else "module"

        has_security_action = any(a in mcts_actions for a in ["VALIDATE_SECURITY", "SYMBOLIC_VALIDATION"])
        has_replace_node = "REPLACE_AST_NODE" in mcts_actions
        has_patch_fix = "PATCH_FIX" in mcts_actions

        if lang == "python":
            return self.generate_python_pipeline_driven(
                intent, ast_analysis, ast_context, solver_insights,
                mcts_actions, safe_target, has_security_action,
                has_replace_node, has_patch_fix
            )
        elif lang == "kotlin":
            return self.generate_kotlin_contextual(intent, safe_target, ast_context.get("class_names", []))
        elif lang == "go":
            return self.generate_go_contextual(intent, safe_target)
        elif lang == "javascript":
            return self.generate_javascript_contextual(intent, safe_target)

        return self.generate_python_pipeline_driven(
            intent, ast_analysis, ast_context, solver_insights,
            mcts_actions, safe_target, has_security_action,
            has_replace_node, has_patch_fix
        )

    def generate_python_pipeline_driven(self, intent, ast_analysis, ast_context,
                                          solver_insights, mcts_actions, safe_target,
                                          has_security_action, has_replace_node,
                                          has_patch_fix):
        """Generate Python code using all pipeline intelligence."""
        orch = self._orchestrator

        if has_replace_node and intent.raw_code:
            target_name = ""
            for step in (intent._plan_steps if hasattr(intent, '_plan_steps') else []):
                if step.action == "REPLACE_AST_NODE" and step.target_node_name:
                    target_name = step.target_node_name
                    break
            if target_name:
                # M1 FIX: Pass raw_code to optimizer
                raw_code = intent.raw_code or ""
                if ast_analysis and not ast_analysis.get("raw_code"):
                    ast_analysis = dict(ast_analysis, raw_code=raw_code)
                return orch._code_transform.optimize_function(target_name, "python", ast_analysis, solver_insights)

        if has_patch_fix and intent.raw_code:
            return orch._code_transform.fix_python(intent.raw_code, ast_analysis, solver_insights)

        if intent.op == OperationType.CREATE and intent.goal == GoalType.SECURITY_HARDEN:
            code = self.generate_security_module(safe_target)
            if solver_insights["status"] == "PROVEN":
                code = f"# Z3 Verified: {solver_insights['validated_constraints']}\n" + code
            return code

        if intent.op == OperationType.CREATE and intent.goal == GoalType.BUG_FIX:
            if intent.raw_code:
                return orch._code_transform.fix_python(intent.raw_code, ast_analysis, solver_insights)

        if intent.op in [OperationType.REFACTOR, OperationType.OPTIMIZE] and intent.raw_code:
            return orch._code_transform.refactor_python(intent.raw_code, ast_analysis, solver_insights)

        if intent.op == OperationType.DEBUG and intent.raw_code:
            return orch._code_transform.fix_python(intent.raw_code, ast_analysis, solver_insights)

        # M1 FIX: Try CodeAssembler for real project generation first
        if intent.op == OperationType.CREATE and hasattr(self, '_assembler') and self._assembler:
            description = str(intent) if intent else safe_target
            try:
                # Extract entities from intent description
                entities = self._extract_entities_from_intent(intent, safe_target)
                result = self._assembler.assemble_project(
                    description, niche_plan=None,
                    project_name=safe_target, entities=entities
                )
                if result and len(result) > 2:
                    # Return the most relevant file (main module)
                    # The full project is available via generate_real_code()
                    main_key = f"blocks/crud_service.py"
                    if main_key in result:
                        logger.info(f"M1: CodeAssembler generated real project for {safe_target}")
                        return result[main_key]
                    # Return first .py file with real content
                    for key, content in result.items():
                        if key.endswith(".py") and len(content) > 100:
                            return content
            except Exception as e:
                logger.debug(f"M1: CodeAssembler fallback to pipeline: {e}")

        existing_functions = ast_context.get("function_names", [])
        existing_classes = ast_context.get("class_names", [])
        needed_imports = set(ast_context.get("import_dependencies", []))
        return self.generate_pipeline_feature_module(
            safe_target, existing_functions, existing_classes,
            needed_imports, solver_insights, mcts_actions
        )

    def generate_pipeline_feature_module(self, safe_target, existing_functions,
                                           existing_classes, needed_imports,
                                           solver_insights, mcts_actions):
        """Generate feature module with REAL _process() via CodeAssembler.

        M1 FIX: No more stubs. The _process() method now contains actual
        CRUD/analytics/notification logic from CodeAssembler.
        """
        import_lines = [
            "from dataclasses import dataclass, field",
            "from typing import List, Optional, Dict, Any",
        ]
        for imp in needed_imports:
            if imp and imp not in ["object", "str", "int", "bool", "list", "dict"]:
                import_lines.append(f"# from your_project import {imp}  # Detected dependency")

        solver_header = ""
        if solver_insights["status"] == "PROVEN":
            constraints_str = "; ".join(str(c) for c in solver_insights["validated_constraints"][:3])
            solver_header = f"# Z3 Verified: {constraints_str}\n"
        elif solver_insights["status"] in ("VIOLATED", "LIKELY_VIOLATED"):
            solver_header = "# Solver detected constraint violations - defensive checks added\n"

        integration_methods = ""
        if existing_functions:
            fn_list = ", ".join(existing_functions[:5])
            cls_list = ", ".join(existing_classes[:3]) if existing_classes else "none"
            integration_methods = f'''
    # Contextual integration with existing code
    # Detected functions: {fn_list}
    # Detected classes: {cls_list}
'''

        null_check_code = ""
        if solver_insights["null_safety_required"]:
            null_check_code = '''
    def _validate_not_none(self, arg_name: str) -> Any:
        """Null-safety guard. Validates by argument name using caller's locals."""
        import inspect
        caller_locals = inspect.currentframe().f_back.f_locals
        value = caller_locals.get(arg_name)
        if value is None:
            raise ValueError(f"{arg_name} must not be None")
        return value
'''

        type_check_code = ""
        if solver_insights["type_safety_required"]:
            type_check_code = '''
    def _validate_type(self, value: Any, expected_type: type, name: str = "value") -> Any:
        """Type-safety guard. Added by solver insight."""
        if not isinstance(value, expected_type):
            raise TypeError(f"{name} expected {expected_type.__name__}, got {type(value).__name__}")
        return value
'''

        security_code = ""
        if solver_insights["critical_target"]:
            security_code = '''
    def _sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Input sanitization for critical target. Added by solver insight."""
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = value.replace("<", "&lt;").replace(">", "&gt;")
            else:
                sanitized[key] = value
        return sanitized
'''

        validation_code = ""
        if "SYMBOLIC_VALIDATION" in mcts_actions:
            validation_code = '''
    def _assert_invariant(self, condition: bool, message: str = "Invariant violation") -> None:
        """Runtime assertion from symbolic validation. Added by MCTS plan."""
        assert condition, f"ZENIC Invariant: {message}"
'''

        div_guard_code = ""
        if solver_insights.get("division_by_zero_risks") or any(
            "division by zero" in str(v).lower()
            for v in solver_insights.get("violated_constraints", [])
        ):
            div_guard_code = '''
    @staticmethod
    def _safe_divide(numerator: Any, denominator: Any, default: Any = None) -> Any:
        """Division with zero-check guard. Added by symbolic execution insight (Z3 proven)."""
        if denominator == 0:
            return default
        return numerator / denominator
'''

        index_guard_code = ""
        if solver_insights.get("index_oob_risks") or any(
            "index out of bounds" in str(v).lower()
            for v in solver_insights.get("violated_constraints", [])
        ):
            index_guard_code = '''
    @staticmethod
    def _safe_index(sequence: Any, index: int, default: Any = None) -> Any:
        """Index access with bounds check. Added by symbolic execution insight."""
        if not hasattr(sequence, '__len__'):
            return default
        if index < 0 or index >= len(sequence):
            return default
        return sequence[index]
'''

        test_code = ""
        concrete_inputs = solver_insights.get("concrete_test_inputs", [])
        if isinstance(concrete_inputs, list) and concrete_inputs:
            test_cases_lines = []
            for i, inputs in enumerate(concrete_inputs[:5]):
                if isinstance(inputs, dict):
                    args_str = ", ".join(f"{k}={v!r}" for k, v in inputs.items())
                    test_cases_lines.append(
                        f"    def test_case_{i+1}(self):\n"
                        f"        result = self.execute({{{args_str}}})\n"
                        f"        assert result.success, f\"Test {i+1} failed: {{result.error}}\""
                    )
            if test_cases_lines:
                test_code = '\n\nclass Test{cls_name}:\n    """Test cases generated from Z3 concrete symbolic inputs."""\n{test_methods}\n'.format(
                    cls_name=safe_target.capitalize(), test_methods="\n\n".join(test_cases_lines)
                )

        # ── M1 FIX: Generate REAL _process() method ──
        real_process_code = self._build_real_process(safe_target, solver_insights, mcts_actions)

        # Build final module with real _process()
        cls_name = safe_target.capitalize()
        table_name = safe_target.lower() + "s"

        module_code = f'''{solver_header}"""
{safe_target} - Feature Module
Generated by ZENIC-AGENTS (Pipeline-Driven Generation)
Pipeline: Solver={solver_insights["solver_type"]}, MCTS actions={len(mcts_actions)}
"""
{chr(10).join(import_lines)}


@dataclass
class Config:
    """Module configuration."""
    name: str = "{safe_target}"
    debug: bool = False
    max_retries: int = 3


@dataclass
class Result:
    """Operation result with error handling."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class {cls_name}Manager:
    """Main module manager - pipeline-driven generation with REAL logic."""
{integration_methods}{null_check_code}{type_check_code}{security_code}{validation_code}{div_guard_code}{index_guard_code}
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._initialized = False

    def initialize(self) -> Result:
        """Initialize the module."""
        try:
            self._initialized = True
            return Result(success=True, data={{"status": "initialized"}})
        except Exception as e:
            return Result(success=False, error=str(e))

    def execute(self, payload: Dict[str, Any]) -> Result:
        """Execute main operation."""
        if not self._initialized:
            return Result(success=False, error="Module not initialized")
        try:
            result_data = self._process(payload)
            return Result(success=True, data=result_data)
        except Exception as e:
            return Result(success=False, error=str(e))
{real_process_code}


if __name__ == "__main__":
    manager = {cls_name}Manager()
    result = manager.initialize()
    print(f"Initialization: {{result.success}}")
{test_code}
'''
        return module_code

    # ================================================================
    #  M1: REAL _process() GENERATION (no more stubs)
    # ================================================================
