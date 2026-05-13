"""
Unit tests for Agent Schemas

Tests dataclass construction, default values, field validation,
and schema relationships across all agent schemas.
"""

import pytest
from dataclasses import fields

from src.core.agents.schemas import (
    IntentInput, IntentOutput,
    ReasoningInput, ReasoningStep, ReasoningOutput,
    BusinessInput, BusinessOutput,
    CodeInput, FileSpec, CodeOutput,
    AutomationInput, TriggerSpec, ActionSpec, ScheduleSpec, AutomationOutput,
    ValidationInput, ValidationIssue, ValidationOutput,
    ContextInput, ContextEntry, ContextOutput,
    CriticalityInput, CriticalityOutput,
)


from .test_schemas_parts import *  # noqa: F401,F403
