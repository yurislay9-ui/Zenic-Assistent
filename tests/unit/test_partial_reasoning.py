"""
ZENIC-AGENTS - PartialReasoningManager Tests

Tests for partial reasoning responses and resumption:
  - build_partial_reasoning_response: payload construction, resumption token
  - resume_from_partial: resumption with valid/expired tokens, subtask execution
  - TTL expiration: old resumption entries are cleaned up
  - State serialization: SubtaskDescriptor reconstruction from dicts/strings
"""

from .test_partial_parts import *
