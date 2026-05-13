"""
ChainExecutor: Execute LogicChains with snapshot/rollback and recovery.
"""

import time
import copy
from typing import Any, Dict, List, Optional, Tuple

from ._imports import (
    RecoveryAction, ChainStatus, StepResult, ChainResult,
    ValidationResult, logger,
)
from .validator import ChainValidator


class ChainExecutor:
    """
    Execute LogicChains with snapshot/rollback support and recovery strategies.

    For each step:
      1. Take a snapshot of current data
      2. Execute the block
      3. If success: continue
      4. If failure: apply recovery strategy
      5. If recovery fails: rollback to snapshot

    This provides transactional semantics for logic chains.
    """

    def __init__(self, validator: Optional[ChainValidator] = None,
                 default_recovery: RecoveryAction = RecoveryAction.ABORT,
                 max_retries: int = 1) -> None:
        self._validator = validator or ChainValidator()
        self._default_recovery = default_recovery
        self._max_retries = max_retries
        self._recovery_strategies: Dict[str, RecoveryAction] = {}
        self._fallback_values: Dict[str, Dict[str, Any]] = {}

    def set_recovery(self, block_name: str, action: RecoveryAction,
                     fallback_value: Optional[Dict[str, Any]] = None) -> None:
        """Set recovery strategy for a specific block."""
        self._recovery_strategies[block_name] = action
        if fallback_value:
            self._fallback_values[block_name] = fallback_value

    def execute(self, chain: Any, initial_data: Optional[Dict[str, Any]] = None,
                context: Optional[Dict[str, Any]] = None,
                validate_first: bool = True) -> ChainResult:
        """
        Execute a LogicChain with full safety guarantees.

        Args:
            chain: LogicChain to execute
            initial_data: Input data
            context: Shared context
            validate_first: Whether to validate before executing

        Returns:
            ChainResult with detailed diagnostics
        """
        start = time.time()
        initial_data = initial_data or {}
        context = context or {}
        chain_result = ChainResult()

        # Step 1: Validate
        if validate_first:
            validation = self._validator.validate(chain, initial_data, context)
            chain_result.validation = validation
            if not validation.can_execute:
                chain_result.status = ChainStatus.FAILED
                chain_result.error = f"Validation failed: {'; '.join(e.message for e in validation.errors)}"
                chain_result.total_duration_ms = (time.time() - start) * 1000
                return chain_result

        # Step 2: Execute with snapshots
        blocks = chain.blocks if hasattr(chain, 'blocks') else []
        current_data = copy.deepcopy(initial_data)
        snapshots: List[Tuple[int, Dict[str, Any]]] = []
        chain_result.status = ChainStatus.RUNNING

        for i, step in enumerate(blocks):
            step_type = step.get("type", "block") if isinstance(step, dict) else "block"

            if step_type == "condition":
                # Condition steps are not directly executable by ChainExecutor;
                # they are evaluated and resolved by the LogicChain itself.
                logger.debug("ChainExecutor: Condition step skipped (not executable)")
                continue

            block = step.get("block", step) if isinstance(step, dict) else step
            if not hasattr(block, 'execute'):
                continue

            block_name = getattr(block, 'name', f'step_{i}')

            # Take snapshot before execution
            snapshot = copy.deepcopy(current_data)
            snapshots.append((i, snapshot))

            # Execute with retry logic
            step_result = self._execute_step(
                block, block_name, i, current_data, context
            )
            chain_result.step_results.append(step_result)

            if step_result.success:
                current_data.update(step_result.data)
                chain_result.steps_completed += 1
            else:
                chain_result.steps_failed += 1

                # Apply recovery strategy
                recovery = self._recovery_strategies.get(
                    block_name, self._default_recovery
                )
                step_result.recovery_action = recovery

                if recovery == RecoveryAction.ABORT:
                    chain_result.status = ChainStatus.FAILED
                    chain_result.error = f"Block '{block_name}' failed: {step_result.error}"
                    break

                elif recovery == RecoveryAction.ROLLBACK:
                    # Rollback to last successful state
                    if snapshots:
                        last_idx, last_data = snapshots[-1]
                        current_data = copy.deepcopy(last_data)
                        chain_result.rollback_count += 1
                        chain_result.status = ChainStatus.ROLLED_BACK
                    break

                elif recovery == RecoveryAction.SKIP:
                    chain_result.steps_skipped += 1
                    step_result.recovered = True
                    continue

                elif recovery == RecoveryAction.FALLBACK:
                    fallback = self._fallback_values.get(block_name,
                                                         {"success": True, "fallback": True})
                    current_data.update(fallback)
                    step_result.recovered = True
                    chain_result.steps_completed += 1
                    continue

                elif recovery == RecoveryAction.RETRY:
                    # Already retried in _execute_step
                    if step_result.retried:
                        chain_result.status = ChainStatus.FAILED
                        chain_result.error = f"Block '{block_name}' failed after retry: {step_result.error}"
                        break

        # Set final status
        if chain_result.status == ChainStatus.RUNNING:
            if chain_result.steps_failed > 0 and chain_result.steps_completed > 0:
                chain_result.status = ChainStatus.PARTIAL
            elif chain_result.steps_failed == 0:
                chain_result.status = ChainStatus.COMPLETED
            else:
                chain_result.status = ChainStatus.FAILED

        chain_result.final_data = current_data
        chain_result.total_duration_ms = (time.time() - start) * 1000
        return chain_result

    def _execute_step(self, block: Any, block_name: str, index: int,
                      data: Dict[str, Any], context: Dict[str, Any]) -> StepResult:
        """Execute a single block with retry support."""
        step_start = time.time()
        snapshot_before = copy.deepcopy(data)
        retried = False

        # First attempt
        try:
            result = block.execute(data, context)
            duration_ms = (time.time() - step_start) * 1000

            if result.get("success", True):
                return StepResult(
                    step_index=index,
                    block_name=block_name,
                    success=True,
                    data=result,
                    duration_ms=duration_ms,
                    snapshot_before=snapshot_before,
                )
            else:
                error = result.get("error", "Block returned success=False")
        except Exception as e:
            error = str(e)
            duration_ms = (time.time() - step_start) * 1000

        # Retry if configured
        if self._max_retries > 0 and self._recovery_strategies.get(
                block_name, self._default_recovery) == RecoveryAction.RETRY:
            retried = True
            logger.info(f"ChainExecutor: Retrying block '{block_name}' after failure")
            try:
                result = block.execute(data, context)
                duration_ms = (time.time() - step_start) * 1000

                if result.get("success", True):
                    return StepResult(
                        step_index=index,
                        block_name=block_name,
                        success=True,
                        data=result,
                        duration_ms=duration_ms,
                        snapshot_before=snapshot_before,
                        retried=True,
                    )
            except Exception as e:
                error = f"{error}; Retry also failed: {str(e)}"
                duration_ms = (time.time() - step_start) * 1000

        return StepResult(
            step_index=index,
            block_name=block_name,
            success=False,
            error=error,
            duration_ms=duration_ms,
            snapshot_before=snapshot_before,
            retried=retried,
        )
