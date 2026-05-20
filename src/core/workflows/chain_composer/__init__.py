"""
ZENIC-AGENTS — DynamicChainComposer: composes & executes workflow chains.

This package re-exports every symbol that the original monolithic
``chain_composer.py`` exported, so existing imports like::

    from src.core.workflows.chain_composer import DynamicChainComposer

continue to work without modification.
"""

from ._composer import DynamicChainComposer, get_chain_composer
from ._types import (
    ChainExecutionResult,
    ChainStatus,
    ChainStep,
    ChainStepResult,
    ChainStepType,
    ChainValidationResult,
    ComposedChain,
)

__all__ = [
    "ChainStep",
    "ChainStepType",
    "ChainStatus",
    "ComposedChain",
    "ChainStepResult",
    "ChainExecutionResult",
    "ChainValidationResult",
    "DynamicChainComposer",
    "get_chain_composer",
]
