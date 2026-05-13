"""
Unit tests for AutomationAgent.

Tests the agent that unifies automation design:
  - Trigger inference (schedule, event, webhook)
  - Action inference (email, http, db, file, etc.)
  - Schedule inference (hourly, daily, weekly, monthly)
  - Condition inference
  - Name extraction
  - to_workflow_dict() legacy compatibility
  - LLM response parsing
  - SmartMemory cache integration
"""

from .test_auto_agent_parts import *
