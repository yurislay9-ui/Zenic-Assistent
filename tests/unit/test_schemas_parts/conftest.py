"""Shared imports for Agent Schemas tests."""

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
