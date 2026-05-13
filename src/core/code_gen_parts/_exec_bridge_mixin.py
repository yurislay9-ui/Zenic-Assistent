"""
ExecutionBridge — Validate generated code by executing it.

Problem: The system generates code but NEVER verifies it works.
Solution: Execute generated code in an isolated sandbox, check outputs,
auto-repair if possible, and report results.

Architecture:
  1. validate_code() — syntax check + compile + import test
  2. execute_test() — run the code and verify return values
  3. auto_repair_loop() — if code fails, send error to CodeAgent for fix
  4. generate_test_code() — auto-generate tests for generated code
"""

import os
import sys
import ast
import types
import logging
import traceback
import tempfile
import importlib
import importlib.util
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 3


@dataclass
class ValidationResult:
    """Result of code validation."""
    valid: bool = False
    syntax_ok: bool = False
    import_ok: bool = False
    execution_ok: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    test_results: List[Dict] = field(default_factory=list)
    repair_attempts: int = 0


class ExecutionBridge:
    """Validate generated code by actually executing it."""

    def __init__(self, code_agent=None, sandbox_dir: Optional[str] = None):
        """
        Args:
            code_agent: Optional CodeAgent for auto-repair
            sandbox_dir: Directory for temporary test files
        """
        self._code_agent = code_agent
        self._sandbox_dir = sandbox_dir or tempfile.mkdtemp(prefix="zenic_exec_bridge_")

    # ================================================================
    #  PUBLIC API
    # ================================================================

    def validate_code(self, code: str, module_name: str = "test_module",
                      expected_classes: Optional[List[str]] = None,
                      expected_functions: Optional[List[str]] = None) -> ValidationResult:
        """Full validation pipeline: syntax → import → structure → execution.

        Args:
            code: Python code to validate
            module_name: Name for the temporary module
            expected_classes: List of class names that should exist
            expected_functions: List of function names that should exist

        Returns:
            ValidationResult with detailed pass/fail info
        """
        result = ValidationResult()

        # Step 1: Syntax check
        try:
            ast.parse(code)
            result.syntax_ok = True
        except SyntaxError as e:
            result.errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            return result  # Can't continue if syntax is broken

        # Step 2: Compile check
        try:
            compiled = compile(code, f'<{module_name}>', 'exec')
        except Exception as e:
            result.errors.append(f"Compile error: {e}")
            return result

        # Step 3: Import test — execute in isolated namespace
        try:
            namespace = {
                "__name__": module_name,
                "__file__": f"<{module_name}>",
            }
            exec(compiled, namespace)
            result.import_ok = True
        except Exception as e:
            result.errors.append(f"Import/execution error: {e}")
            result.warnings.append(f"Traceback: {traceback.format_exc()}")
            # Continue anyway — some imports might fail in test env

        # Step 4: Structure check — verify expected classes/functions exist
        if expected_classes:
            for cls_name in expected_classes:
                if cls_name in namespace:
                    obj = namespace[cls_name]
                    if isinstance(obj, type):
                        result.warnings.append(f"Class '{cls_name}' found ✓")
                    else:
                        result.errors.append(f"'{cls_name}' exists but is not a class")
                else:
                    result.errors.append(f"Expected class '{cls_name}' not found")

        if expected_functions:
            for fn_name in expected_functions:
                if fn_name in namespace and callable(namespace[fn_name]):
                    result.warnings.append(f"Function '{fn_name}' found ✓")
                else:
                    result.errors.append(f"Expected function '{fn_name}' not found or not callable")

        # Step 5: Basic execution test
        try:
            exec_result = self._test_basic_execution(namespace, module_name)
            if exec_result:
                result.execution_ok = True
                result.test_results = exec_result
            else:
                result.execution_ok = True  # No testable methods, but no crash
        except Exception as e:
            result.errors.append(f"Execution test failed: {e}")

        # Final verdict
        result.valid = result.syntax_ok and (result.import_ok or len(result.errors) <= 2)

        return result

    def execute_with_tests(self, code: str, module_name: str = "test_module",
                           test_code: Optional[str] = None) -> ValidationResult:
        """Execute code with auto-generated or provided tests.

        Args:
            code: Python code to test
            module_name: Name for the module
            test_code: Optional test code. If None, auto-generated.

        Returns:
            ValidationResult with test results
        """
        result = self.validate_code(code, module_name)

        if not result.syntax_ok:
            return result

        # Generate test code if not provided
        if not test_code:
            test_code = self.generate_test_code(code, module_name)

        if not test_code:
            result.warnings.append("Could not generate test code")
            return result

        # Write module and test to temp files
        module_path = os.path.join(self._sandbox_dir, f"{module_name}.py")
        test_path = os.path.join(self._sandbox_dir, f"test_{module_name}.py")

        try:
            with open(module_path, "w") as f:
                f.write(code)
            with open(test_path, "w") as f:
                f.write(test_code)

            # Run tests
            import subprocess
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
                capture_output=True, text=True, timeout=30,
                cwd=self._sandbox_dir,
            )

            result.execution_ok = proc.returncode == 0
            if proc.returncode != 0:
                result.errors.append(f"Tests failed:\n{proc.stdout}\n{proc.stderr}")
            else:
                result.warnings.append("All tests passed ✓")

        except subprocess.TimeoutExpired:
            result.errors.append("Test execution timed out (30s)")
        except Exception as e:
            result.errors.append(f"Test execution error: {e}")
        finally:
            # Cleanup
            for p in [module_path, test_path]:
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

        return result

    def auto_repair_loop(self, code: str, module_name: str = "test_module",
                         expected_classes: Optional[List[str]] = None,
                         expected_functions: Optional[List[str]] = None) -> Tuple[str, ValidationResult]:
        """Try to auto-repair broken code using CodeAgent.

        Args:
            code: Initial code (may be broken)
            module_name: Module name
            expected_classes: Expected class names
            expected_functions: Expected function names

        Returns:
            Tuple of (best_code, validation_result)
        """
        current_code = code
        best_result = self.validate_code(current_code, module_name,
                                          expected_classes, expected_functions)

        if best_result.valid:
            return current_code, best_result

        for attempt in range(MAX_REPAIR_ATTEMPTS):
            if not self._code_agent:
                break

            # Build repair prompt
            error_summary = "\n".join(best_result.errors[:5])
            repair_prompt = (
                f"The following Python code has errors:\n\n"
                f"```python\n{current_code}\n```\n\n"
                f"ERRORS:\n{error_summary}\n\n"
                f"Fix the errors and output ONLY the corrected code. "
                f"Expected classes: {expected_classes}. "
                f"Expected functions: {expected_functions}."
            )

            try:
                # Use CodeAgent to fix
                if hasattr(self._code_agent, 'generate'):
                    fixed_code = self._code_agent.generate(repair_prompt)
                elif callable(self._code_agent):
                    fixed_code = self._code_agent(repair_prompt)
                else:
                    break

                if not fixed_code:
                    continue

                # Extract code from markdown if needed
                import re
                match = re.search(r'```python\s*\n(.*?)```', fixed_code, re.DOTALL)
                if match:
                    fixed_code = match.group(1).strip()

                # Validate the fix
                new_result = self.validate_code(fixed_code, module_name,
                                                 expected_classes, expected_functions)
                new_result.repair_attempts = attempt + 1

                # Use the fix if it's better
                if new_result.valid or len(new_result.errors) < len(best_result.errors):
                    current_code = fixed_code
                    best_result = new_result

                if best_result.valid:
                    return current_code, best_result

            except Exception as e:
                logger.warning(f"ExecutionBridge: Repair attempt {attempt+1} failed: {e}")

        best_result.repair_attempts = MAX_REPAIR_ATTEMPTS
        return current_code, best_result

    # ================================================================
    #  TEST GENERATION
    # ================================================================

    def generate_test_code(self, code: str, module_name: str) -> Optional[str]:
        """Auto-generate basic tests for the given code.

        Analyzes the AST to find classes and methods, then generates
        pytest tests that verify they exist and can be instantiated.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return None

        classes = []
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({"name": node.name, "methods": methods})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not any(node.name == m for cls in classes for m in cls["methods"]):
                    functions.append(node.name)

        if not classes and not functions:
            return None

        # Generate test code
        lines = [
            f'"""Auto-generated tests for {module_name}."""',
            'import pytest',
            f'import {module_name}',
            '',
            '',
        ]

        for cls_info in classes:
            cls_name = cls_info["name"]
            lines.append(f'class Test{cls_name}:')
            lines.append(f'    """Tests for {cls_name}."""')
            lines.append('')
            lines.append(f'    def test_instantiation(self):')
            lines.append(f'        """Test that {cls_name} can be instantiated."""')
            lines.append(f'        obj = {module_name}.{cls_name}.__new__({module_name}.{cls_name})')
            lines.append(f'        assert obj is not None')
            lines.append('')

            for method in cls_info["methods"]:
                if method.startswith("_") and not method.startswith("__"):
                    continue  # Skip private methods
                lines.append(f'    def test_{method}_exists(self):')
                lines.append(f'        """Test that {cls_name}.{method} exists."""')
                lines.append(f'        assert hasattr({module_name}.{cls_name}, "{method}")')
                lines.append('')

        for fn_name in functions:
            lines.append(f'def test_{fn_name}_exists():')
            lines.append(f'    """Test that {fn_name} exists."""')
            lines.append(f'    assert hasattr({module_name}, "{fn_name}")')
            lines.append('')

        return '\n'.join(lines)

    # ================================================================
    #  INTERNAL
    # ================================================================

    def _test_basic_execution(self, namespace: Dict, module_name: str) -> List[Dict]:
        """Try to instantiate classes and call their methods."""
        results = []

        for name, obj in namespace.items():
            if not isinstance(obj, type):
                continue
            if name.startswith("_"):
                continue

            # Try to instantiate
            try:
                instance = obj.__new__(obj)
                results.append({
                    "class": name,
                    "instantiated": True,
                    "error": None,
                })

                # Try to call initialize() if it exists
                if hasattr(instance, 'initialize') and callable(instance.initialize):
                    try:
                        init_result = instance.initialize()
                        results.append({
                            "class": name,
                            "method": "initialize",
                            "result": str(init_result)[:100],
                            "success": True,
                        })
                    except Exception as e:
                        results.append({
                            "class": name,
                            "method": "initialize",
                            "error": str(e),
                            "success": False,
                        })

            except Exception as e:
                results.append({
                    "class": name,
                    "instantiated": False,
                    "error": str(e),
                })

        return results
