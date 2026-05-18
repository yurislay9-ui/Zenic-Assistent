"""
ZENIC-AGENTS — Chain validation logic for the DynamicChainComposer.

Standalone validation function that checks a composed chain before
execution.  Extracted from DynamicChainComposer so it can be tested
and reused independently.
"""

from __future__ import annotations

from ._types import (
    ChainStepType,
    ChainValidationResult,
    ComposedChain,
)


def validate_chain(chain: ComposedChain) -> ChainValidationResult:
    """Validate a composed chain before execution.

    Checks:
      - Chain has at least one step
      - Step IDs are unique
      - Step types are valid
      - next_step_id references exist (or are empty)
      - No orphan steps (all reachable from first step)
      - Warnings for very long chains or missing conditions on branches
    """
    result = ChainValidationResult(valid=True, errors=[], warnings=[])

    # 1. Empty chain
    if not chain.steps:
        result.errors.append("Chain has no steps")
        result.valid = False
        return result

    # 2. Unique step IDs
    step_ids = {s.step_id for s in chain.steps}
    if len(step_ids) != len(chain.steps):
        result.errors.append("Duplicate step IDs detected")
        result.valid = False

    # 3. Valid step types
    for step in chain.steps:
        if not isinstance(step.step_type, ChainStepType):
            try:
                ChainStepType(step.step_type)
            except ValueError:
                result.errors.append(
                    f"Step '{step.step_id}' has invalid step_type: {step.step_type}"
                )
                result.valid = False

    # 4. next_step_id references
    for step in chain.steps:
        if step.next_step_id and step.next_step_id not in step_ids:
            result.errors.append(
                f"Step '{step.step_id}' references non-existent next_step_id '{step.next_step_id}'"
            )
            result.valid = False

    # 5. Orphan detection (BFS from first step)
    if chain.steps:
        first_id = chain.steps[0].step_id
        visited: set[str] = set()
        queue = [first_id]
        steps_by_id = {s.step_id: s for s in chain.steps}
        while queue:
            current_id = queue.pop(0)
            if current_id in visited or current_id not in steps_by_id:
                continue
            visited.add(current_id)
            nxt = steps_by_id[current_id].next_step_id
            if nxt:
                queue.append(nxt)
        orphans = step_ids - visited
        if orphans:
            result.warnings.append(
                f"Orphan steps not reachable from first step: {orphans}"
            )

    # 6. Length warning
    if len(chain.steps) > 10:
        result.warnings.append(
            f"Chain has {len(chain.steps)} steps — consider splitting into sub-chains"
        )

    # 7. Condition step without condition_expr
    for step in chain.steps:
        if step.step_type == ChainStepType.CONDITION and not step.condition_expr:
            result.warnings.append(
                f"Condition step '{step.step_id}' has no condition_expr"
            )

    if result.errors:
        result.valid = False

    return result
