"""
ZENIC-AGENTS — B2 Auto-chained Workflows Package.

Provides dynamic chain composition, template management, inter-workflow
handoff, and conditional branching for building production-grade
automated workflow pipelines.

Modules:
  chain_composer   — DynamicChainComposer: composes & executes workflow chains
  chain_templates  — ChainTemplateLibrary: reusable workflow templates
  inter_workflow   — InterWorkflowHandoff: passes output between chains
  conditional_branch — ConditionalBranching: if/then/else logic in chains
"""

from .chain_composer import (
    ChainStep,
    ChainStepType,
    ChainStatus,
    ComposedChain,
    ChainStepResult,
    ChainExecutionResult,
    ChainValidationResult,
    DynamicChainComposer,
    get_chain_composer,
)

from .chain_templates import (
    ChainTemplate,
    TemplateStep,
    TemplateVariable,
    TemplateCategory,
    ChainTemplateLibrary,
    get_template_library,
)

from .inter_workflow import (
    HandoffRule,
    HandoffResult,
    FieldMapping,
    InterWorkflowHandoff,
    get_inter_workflow_handoff,
)

from .conditional_branch import (
    BranchRule,
    BranchCondition,
    ConditionalBranching,
    get_conditional_branching,
)

__all__ = [
    # chain_composer
    "ChainStep",
    "ChainStepType",
    "ChainStatus",
    "ComposedChain",
    "ChainStepResult",
    "ChainExecutionResult",
    "ChainValidationResult",
    "DynamicChainComposer",
    "get_chain_composer",
    # chain_templates
    "ChainTemplate",
    "TemplateStep",
    "TemplateVariable",
    "TemplateCategory",
    "ChainTemplateLibrary",
    "get_template_library",
    # inter_workflow
    "HandoffRule",
    "HandoffResult",
    "FieldMapping",
    "InterWorkflowHandoff",
    "get_inter_workflow_handoff",
    # conditional_branch
    "BranchRule",
    "BranchCondition",
    "ConditionalBranching",
    "get_conditional_branching",
]
