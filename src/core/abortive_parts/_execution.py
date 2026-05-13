"""
AbortiveProtocol execute_subtask method mixin.
"""

import time
import logging

from ._imports import (
    logger, SubtaskDescriptor, get_projects_dir,
    MAX_DEEP_SUBTASKS, SUBTASK_SANDBOX_TTL_MULTIPLIER, SUBTASK_SANDBOX_TTL_MIN,
)


class ExecutionMixin:
    """Subtask execution methods for AbortiveProtocol."""

    async def execute_subtask(self, subtask, depth=0, max_depth=2):
        """
        Execute a single subtask through the full pipeline.

        Accepts both SubtaskDescriptor (enriched) and str (legacy).
        Uses StepDispatcher for unified step execution instead of
        duplicating the dispatch logic.
        """
        orch = self._orchestrator

        # Handle both SubtaskDescriptor and str (backward compatible)
        if isinstance(subtask, SubtaskDescriptor):
            subtask_msg = subtask.message
            subtask_context = subtask
            depth = subtask.depth if subtask.depth > 0 else depth
        else:
            subtask_msg = str(subtask)
            subtask_context = None

        if depth >= max_depth:
            return {"status": "MAX_DEPTH_REACHED", "code": "", "message": subtask_msg}

        try:
            sub_intent = orch.parser.parse(subtask_msg)
        except Exception as e:
            return {"status": "ERROR", "code": "", "message": f"Parse error: {e}"}

        sub_ast = {}
        if sub_intent.raw_code:
            sub_ast = orch.ast_engine.analyze_structure(sub_intent.raw_code, sub_intent.language)

        # Cache check
        cache_hit = orch.cache.lookup(sub_intent, sub_intent.raw_code, sub_intent.language)
        if cache_hit:
            return {"status": "CACHED", "code": cache_hit["data"].get("code", "")}

        sub_routing = orch.router.route(sub_intent)
        sub_plan = orch.planner.generate_plan(sub_routing)

        if sub_plan.solver_status == "TIMEOUT_SUBDIVIDE_REQUIRED":
            # Recursive subdivision
            deeper_subtasks = self.generate_subtasks(sub_intent, sub_ast, sub_plan)
            results = []
            for ds in deeper_subtasks[:MAX_DEEP_SUBTASKS]:
                result = await self.execute_subtask(ds, depth + 1, max_depth)
                results.append(result)
            combined = self.merge_subtask_results(results, sub_intent.language)
            return combined

        # Execute plan steps using StepDispatcher (unified logic)
        code = sub_intent.raw_code or ""
        explanations = []
        lang = sub_intent.language

        result_code, code, explanations = await self._step_dispatcher.execute_plan_steps(
            sub_plan, sub_intent, code, explanations, lang, sub_ast,
        )

        final_code = result_code if result_code else code

        # Sandbox validation con workspace AISLADO para subtask
        subtask_workspace = orch._isolation_manager.create_workspace(
            ttl_seconds=max(orch.sandbox.timeout_seconds * SUBTASK_SANDBOX_TTL_MULTIPLIER, SUBTASK_SANDBOX_TTL_MIN)
        )
        p_dir = str(get_projects_dir())
        orch.ledger.snapshot(sub_intent.target, p_dir, workspace=subtask_workspace)
        trial = await orch.sandbox.validate_code(final_code, lang, sub_intent.target)

        if trial.status == "PASS" and final_code:
            node = orch.ledger.commit(sub_intent.target, final_code, p_dir,
                                       workspace=subtask_workspace)
            orch._isolation_manager.release_workspace(subtask_workspace.sandbox_id)
            orch.cache.save(sub_intent, "PROVEN",
                          {"h": node.hash_sha256[:8], "code": final_code},
                          final_code, lang)
            return {"status": "SUCCESS", "code": final_code, "hash": node.hash_sha256[:12],
                    "explanations": explanations}
        elif trial.status == "FAIL_K_PATH":
            orch.ledger.rollback(sub_intent.target, p_dir, workspace=subtask_workspace)
            orch._isolation_manager.release_workspace(subtask_workspace.sandbox_id)
            return {"status": "K_PATH_EXCEEDED", "code": final_code,
                    "error": trial.error_message, "explanations": explanations}
        else:
            orch.ledger.rollback(sub_intent.target, p_dir, workspace=subtask_workspace)
            orch._isolation_manager.release_workspace(subtask_workspace.sandbox_id)
            return {"status": "ROLLBACK", "code": final_code,
                    "error": trial.error_message if hasattr(trial, 'error_message') else "Sandbox validation failed",
                    "explanations": explanations}
