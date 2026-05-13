"""Mixin: Resume from partial reasoning for PartialReasoningManager."""

import gc
import time

from ._imports import get_projects_dir, SubtaskDescriptor, OperationType, GoalType


class ResumeMixin:
    """Mixin providing resume-from-partial execution."""

    async def resume_from_partial(self, resumption_token, subtask_index=None):
        """
        Resume execution from a partial reasoning state (Gap 5 Fix).

        Takes a resumption_token from a previous PARTIAL_REASONING response
        and re-executes the remaining subtasks that haven't succeeded yet,
        then combines results and returns the final output.

        MEJORA: Now uses isolated workspaces and preserves SubtaskDescriptor
        context from parent pipeline (solver insights, MCTS hints, violations).

        Args:
            resumption_token: The token from a previous PARTIAL_REASONING response
            subtask_index: If provided, only re-execute this specific subtask index.
                          If None, re-execute all non-successful subtasks.

        Returns:
            dict with the same format as execute() or handle_abortive_protocol()
        """
        start_time = time.time()
        orch = self._orchestrator

        # Lookup resumption state
        with orch._resumptions_lock:
            state = orch._pending_resumptions.get(resumption_token)
            if not state:
                return {
                    "status": "ERROR",
                    "code": "",
                    "hash": "N/A",
                    "error": f"Invalid or expired resumption token: {resumption_token[:8]}...",
                    "processing_time_ms": 0,
                }

        original_intent_data = state["original_intent"]
        previous_results = state.get("subtask_results", [])
        partial_code = state.get("partial_code", "")
        subtasks_raw = state.get("subtasks", [])

        # Reconstruct SubtaskDescriptors from serialized state
        subtasks = []
        for st in subtasks_raw:
            if isinstance(st, SubtaskDescriptor):
                subtasks.append(st)
            elif isinstance(st, dict):
                # Deserialize from dict (e.g., from JSON)
                subtasks.append(SubtaskDescriptor(
                    message=st.get("message", ""),
                    target=st.get("target", ""),
                    operation=st.get("operation", ""),
                    goal=st.get("goal", ""),
                    solver_insights=st.get("solver_insights", {}),
                    mcts_hints=st.get("mcts_hints", []),
                    parent_violations=st.get("parent_violations", []),
                    parent_context=st.get("parent_context", {}),
                    depth=st.get("depth", 0),
                ))
            elif isinstance(st, str):
                # Legacy string subtask
                subtasks.append(SubtaskDescriptor(message=st))
            else:
                subtasks.append(SubtaskDescriptor(message=str(st)))

        # Reconstruct intent
        from src.core.shared.contracts import IntentPayload
        intent = IntentPayload(
            op=original_intent_data.get("op", OperationType.SEARCH),
            target=original_intent_data.get("target", "unknown"),
            goal=original_intent_data.get("goal", GoalType.FEATURE_ADD),
            language=original_intent_data.get("language", "python"),
            raw_code=original_intent_data.get("raw_code", ""),
            scrap_query=original_intent_data.get("scrap_query", ""),
            confidence=original_intent_data.get("confidence", 0.0),
        )

        # Determine which subtasks to re-execute
        if subtask_index is not None:
            # Re-execute only the specified subtask
            indices_to_run = [subtask_index] if 0 <= subtask_index < len(subtasks) else []
        else:
            # Re-execute all subtasks that didn't succeed
            indices_to_run = []
            for i, result in enumerate(previous_results):
                if isinstance(result, dict) and result.get("status") not in ("SUCCESS", "CACHED"):
                    indices_to_run.append(i)
            # Also include any subtasks beyond previous_results length
            for i in range(len(previous_results), len(subtasks)):
                indices_to_run.append(i)

        if not indices_to_run:
            # All subtasks already succeeded; just combine and validate
            return await self._resume_all_succeeded(
                orch, resumption_token, partial_code, previous_results,
                intent, start_time
            )

        # Execute remaining subtasks with enriched context
        new_results = list(previous_results)  # Copy existing results
        # Extend list to accommodate indices beyond current length
        while len(new_results) < len(subtasks):
            new_results.append(None)
        for idx in indices_to_run:
            if idx < len(subtasks):
                try:
                    result = await orch._abortive.execute_subtask(subtasks[idx], depth=0, max_depth=2)
                    new_results[idx] = result
                except Exception as e:
                    new_results[idx] = {
                        "status": "ERROR",
                        "code": "",
                        "message": str(e),
                    }

        gc.collect()

        # Combine all results (including previously successful ones)
        combined_code = orch._abortive.merge_subtask_results(new_results, intent.language)

        # Use isolated workspace for combined result validation
        resume_workspace = orch._isolation_manager.create_workspace(ttl_seconds=180)

        if combined_code:
            return await self._resume_with_code(
                orch, resumption_token, intent, combined_code, new_results,
                indices_to_run, resume_workspace, start_time
            )

        elapsed = int((time.time() - start_time) * 1000)
        orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
        return {
            "status": "PARTIAL_REASONING",
            "code": "",
            "hash": "N/A",
            "error": "No code produced after resumption",
            "processing_time_ms": elapsed,
            "subtasks": new_results,
            "resumption": {
                "token": resumption_token,
                "completed_subtasks": sum(
                    1 for r in new_results
                    if isinstance(r, dict) and r.get("status") in ("SUCCESS", "CACHED")
                ),
                "total_subtasks": len(new_results),
            },
        }

    async def _resume_all_succeeded(self, orch, resumption_token, partial_code,
                                     previous_results, intent, start_time):
        """Handle resume when all subtasks already succeeded."""
        combined_code = partial_code if partial_code else orch._abortive.merge_subtask_results(
            previous_results, intent.language
        )
        if combined_code:
            resume_workspace = orch._isolation_manager.create_workspace(ttl_seconds=120)
            p_dir = str(get_projects_dir())
            orch.ledger.snapshot(intent.target, p_dir, workspace=resume_workspace)
            trial = await orch.sandbox.validate_code(combined_code, intent.language, intent.target)
            if trial.status == "PASS":
                node = orch.ledger.commit(intent.target, combined_code, p_dir, workspace=resume_workspace)
                orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
                with orch._resumptions_lock:
                    orch._pending_resumptions.pop(resumption_token, None)
                elapsed = int((time.time() - start_time) * 1000)
                return {
                    "status": "SUCCESS", "code": combined_code,
                    "hash": node.hash_sha256[:12], "error": "",
                    "processing_time_ms": elapsed,
                    "explanations": ["Resumed partial reasoning: all subtasks completed successfully."],
                }
            else:
                orch.ledger.rollback(intent.target, p_dir, workspace=resume_workspace)
                orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
        elapsed = int((time.time() - start_time) * 1000)
        return {
            "status": "PARTIAL_REASONING",
            "code": combined_code,
            "hash": "N/A",
            "error": "Resumed but combined result still fails validation",
            "processing_time_ms": elapsed,
        }

    async def _resume_with_code(self, orch, resumption_token, intent, combined_code,
                                 new_results, indices_to_run, resume_workspace, start_time):
        """Handle resume when combined code is available."""
        p_dir = str(get_projects_dir())
        orch.ledger.snapshot(intent.target, p_dir, workspace=resume_workspace)
        trial = await orch.sandbox.validate_code(combined_code, intent.language, intent.target)

        if trial.status == "PASS" and combined_code:
            node = orch.ledger.commit(intent.target, combined_code, p_dir, workspace=resume_workspace)
            orch.cache.save(intent, "PROVEN",
                          {"h": node.hash_sha256[:8], "code": combined_code},
                          combined_code, intent.language)
            elapsed = int((time.time() - start_time) * 1000)

            # Remove resumption state since we succeeded
            with orch._resumptions_lock:
                orch._pending_resumptions.pop(resumption_token, None)
            orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)

            return {
                "status": "SUCCESS",
                "code": combined_code,
                "hash": node.hash_sha256[:12],
                "error": "",
                "processing_time_ms": elapsed,
                "subtasks": new_results,
                "explanations": [
                    f"Resumed partial reasoning: {len(indices_to_run)} subtasks re-executed.",
                    f"Combined result passes sandbox validation.",
                ],
                "warnings": trial.warnings,
                "metrics": trial.metrics,
                "paths_explored": trial.paths_explored,
                "paths_pruned": trial.paths_pruned,
            }
        else:
            orch.ledger.rollback(intent.target, p_dir, workspace=resume_workspace)
            orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
            # Update the resumption state with new results
            with orch._resumptions_lock:
                orch._pending_resumptions[resumption_token]["subtask_results"] = new_results
                orch._pending_resumptions[resumption_token]["partial_code"] = combined_code
            elapsed = int((time.time() - start_time) * 1000)
            return {
                "status": "PARTIAL_REASONING",
                "code": combined_code,
                "hash": "N/A",
                "error": trial.error_message if hasattr(trial, 'error_message') else "Sandbox validation failed after resume",
                "processing_time_ms": elapsed,
                "subtasks": new_results,
                "resumption": {
                    "token": resumption_token,
                    "completed_subtasks": sum(
                        1 for r in new_results
                        if isinstance(r, dict) and r.get("status") in ("SUCCESS", "CACHED")
                    ),
                    "total_subtasks": len(new_results),
                },
                "explanations": [
                    f"Resumed partial reasoning: {len(indices_to_run)} subtasks re-executed.",
                    f"Combined result still fails sandbox validation.",
                ],
                "warnings": trial.warnings if hasattr(trial, 'warnings') else [],
            }
