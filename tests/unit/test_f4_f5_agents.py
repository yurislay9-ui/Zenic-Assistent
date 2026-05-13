"""
Unit tests for CodeAgent, AutomationAgent, ValidationAgent (Phase F4-F5)

Tests the 3 new AI agents that replace legacy modules:
  - CodeAgent replaces CodeGenerator + CodeTransformer
  - AutomationAgent replaces AutomationEngine keyword inference
  - ValidationAgent replaces ChainValidator regex patterns

All fallback logic is deterministic (no LLM needed).
Only AgentRunner is mocked for *_with_runner methods.

Modularized into test_f4_f5_parts/ sub-directory.
"""

# Re-export all test classes from sub-modules for backward compatibility
from .test_f4_f5_parts import *

# Re-export fixtures so they're available when running via this facade
from .test_f4_f5_parts.conftest import code_agent, automation_agent, validation_agent
