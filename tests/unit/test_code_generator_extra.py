"""
Unit tests for CodeGenerator (Extended Coverage)

Tests additional methods and edge cases not covered by the existing
test_code_generator.py. Focuses on:
- extract_solver_insights with various proof statuses
- extract_ast_context with various connection types
- extract_symbolic_insights
- Language-specific code generators (Kotlin, Go, JavaScript)
- Pipeline-driven feature module generation
- Security module generation
- Edge cases and error handling

Modularized into test_code_gen_extra_parts/ sub-directory.
"""

# Re-export all test classes from sub-modules for backward compatibility
from .test_code_gen_extra_parts import *

# Re-export fixtures so they're available when running via this facade
from .test_code_gen_extra_parts.conftest import (
    code_gen, create_intent, security_intent, bugfix_intent, refactor_intent, debug_intent,
)
