"""
AbortiveProtocol generate_subtasks method mixin.
"""

import logging

from ._imports import (
    logger, OperationType, SubtaskDescriptor,
)


class SubtaskGenerationMixin:
    """Subtask generation methods for AbortiveProtocol."""

    def generate_subtasks(self, intent, ast_analysis, plan=None):
        """
        Genera subtareas enriquecidas (SubtaskDescriptor) a partir de una tarea
        que excedio el presupuesto del solver.
        """
        orch = self._orchestrator
        # Extract parent pipeline context
        solver_insights = orch._code_gen.extract_solver_insights(plan.solver_proof) if plan else {}
        mcts_hints = []
        if plan and plan.steps:
            mcts_hints = [s.action for s in plan.steps[:3]]

        parent_violations = []
        if plan and plan.solver_proof and isinstance(plan.solver_proof, dict):
            for key in ["null_safety", "type_safety", "invariant_safety"]:
                sub_result = plan.solver_proof.get(key)
                if isinstance(sub_result, dict) and not sub_result.get("verified", True):
                    parent_violations.append(f"{key}: {sub_result.get('proof', 'violation detected')}")

        parent_context = {
            "ast_analysis": ast_analysis,
            "solver_status": plan.solver_status if plan else "UNKNOWN",
            "mcts_simulations": plan.mcts_simulations if plan else 0,
            "mcts_depth": plan.mcts_depth_reached if plan else 0,
        }

        subtasks = []

        if intent.raw_code:
            function_names = ast_analysis.get("function_names", [])
            if function_names:
                for fn_name in function_names:
                    subtasks.append(SubtaskDescriptor(
                        message=f"{intent.op.lower()} function {fn_name} in {intent.target} "
                                f"with goal {intent.goal}",
                        target=fn_name,
                        operation=intent.op,
                        goal=intent.goal,
                        solver_insights=solver_insights,
                        mcts_hints=mcts_hints,
                        parent_violations=parent_violations,
                        parent_context=parent_context,
                        depth=0,
                    ))
            else:
                subtasks.append(SubtaskDescriptor(
                    message=f"analyze structure of {intent.target}",
                    target=intent.target,
                    operation="ANALYZE",
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
                subtasks.append(SubtaskDescriptor(
                    message=f"{intent.op.lower()} {intent.target} with goal {intent.goal}",
                    target=intent.target,
                    operation=intent.op,
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
        else:
            subtasks = self._generate_subtasks_by_operation(
                intent, solver_insights, mcts_hints,
                parent_violations, parent_context,
            )

        if not subtasks:
            subtasks.append(SubtaskDescriptor(
                message=f"process {intent.target}",
                target=intent.target,
                operation=intent.op,
                goal=intent.goal,
                solver_insights=solver_insights,
                mcts_hints=mcts_hints,
                parent_violations=parent_violations,
                parent_context=parent_context,
                depth=0,
            ))

        return subtasks

    def _generate_subtasks_by_operation(self, intent, solver_insights,
                                         mcts_hints, parent_violations,
                                         parent_context):
        """Generate subtasks based on operation type."""
        subtasks = []

        if intent.op == OperationType.CREATE:
            subtasks = self._subtasks_create(
                intent, solver_insights, mcts_hints,
                parent_violations, parent_context,
            )
        elif intent.op in [OperationType.REFACTOR, OperationType.OPTIMIZE]:
            subtasks = self._subtasks_refactor(
                intent, solver_insights, mcts_hints,
                parent_violations, parent_context,
            )
        elif intent.op == OperationType.DEBUG:
            subtasks = self._subtasks_debug(
                intent, solver_insights, mcts_hints,
                parent_violations, parent_context,
            )
        else:
            subtasks = self._subtasks_generic(
                intent, solver_insights, mcts_hints,
                parent_violations, parent_context,
            )

        return subtasks

    @staticmethod
    def _make_descriptor(message, target, operation, goal, solver_insights,
                         mcts_hints, parent_violations, parent_context, depth=0):
        """Helper to create a SubtaskDescriptor with common fields."""
        return SubtaskDescriptor(
            message=message, target=target, operation=operation, goal=goal,
            solver_insights=solver_insights, mcts_hints=mcts_hints,
            parent_violations=parent_violations, parent_context=parent_context,
            depth=depth,
        )

    def _subtasks_create(self, intent, si, mh, pv, pc):
        """CREATE operation subtasks."""
        mk = self._make_descriptor
        return [
            mk(f"create interfaces and types for {intent.target}", intent.target,
               "CREATE", "INTERFACE_DEFINITION", si, mh, pv, pc),
            mk(f"implement core logic for {intent.target}", intent.target,
               "CREATE", "IMPLEMENTATION", si, mh, pv, pc),
            mk(f"add error handling and validation for {intent.target}", intent.target,
               "CREATE", "SECURITY_HARDEN", si, mh, pv, pc),
        ]

    def _subtasks_refactor(self, intent, si, mh, pv, pc):
        """REFACTOR/OPTIMIZE operation subtasks."""
        mk = self._make_descriptor
        return [
            mk(f"analyze patterns in {intent.target}", intent.target,
               "ANALYZE", intent.goal, si, mh, pv, pc),
            mk(f"apply optimizations to {intent.target}", intent.target,
               intent.op, intent.goal, si, mh, pv, pc),
        ]

    def _subtasks_debug(self, intent, si, mh, pv, pc):
        """DEBUG operation subtasks."""
        mk = self._make_descriptor
        return [
            mk(f"trace execution in {intent.target}", intent.target,
               "DEBUG", "TRACE", si, mh, pv, pc),
            mk(f"apply minimal fix to {intent.target}", intent.target,
               "DEBUG", "BUG_FIX", si, mh, pv, pc),
        ]

    def _subtasks_generic(self, intent, si, mh, pv, pc):
        """Generic operation subtasks (fallback)."""
        mk = self._make_descriptor
        return [
            mk(f"analyze {intent.target} part 1", intent.target,
               "ANALYZE", intent.goal, si, mh, pv, pc),
            mk(f"analyze {intent.target} part 2", intent.target,
               "ANALYZE", intent.goal, si, mh, pv, pc),
        ]
