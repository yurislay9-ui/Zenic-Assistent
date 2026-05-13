"""Mixin: Step building and solver status for APAPlanner.

FIX (Phase 2): MCTS result (best_action_hint) is now USED to:
1. Prioritize MCTS-recommended steps by moving them earlier in the plan
2. Insert MCTS-suggested actions that aren't in the default step list
3. Record the MCTS hint in step metadata for downstream consumers

Previously, best_action_hint was received but completely ignored,
wasting hundreds of MCTS simulations.
"""

from ._imports import PlanStep, OperationType, RoutePath


# Mapping from MCTS action names to step properties
_MCTS_ACTION_MAP = {
    "ANALYZE_STRUCTURE": {"action": "ANALYZE_STRUCTURE", "source": "LOCAL_GRAPH",
                           "constraints": {"depth": "full", "include_metrics": True}},
    "SCRAPE_PATTERNS": {"action": "SCRAPE_PATTERNS", "source": "GITHUB_SCRAPE",
                         "constraints": {"query": "", "max_results": 3}},
    "GENERATE_CODE": {"action": "GENERATE_CODE", "source": "TEMPLATE_ENGINE",
                       "constraints": {"require_validation": True, "security_check": True}},
    "VALIDATE_SECURITY": {"action": "SYMBOLIC_VALIDATION", "source": "SANDBOX",
                           "constraints": {"k_path_limit": 10, "mock_externals": True, "security_focus": True}},
    "SYMBOLIC_VALIDATION": {"action": "SYMBOLIC_VALIDATION", "source": "SANDBOX",
                             "constraints": {"k_path_limit": 10, "mock_externals": True}},
    "ANALYZE_PATTERNS": {"action": "ANALYZE_PATTERNS", "source": "LOCAL_GRAPH",
                          "constraints": {"detect_smells": True, "metrics": True}},
    "REPLACE_AST_NODE": {"action": "REPLACE_AST_NODE", "source": "SURGICAL_GRAPH",
                          "constraints": {"preserve_interface": True, "security_check": True}},
    "VALIDATE_INTERFACE": {"action": "SYMBOLIC_VALIDATION", "source": "SANDBOX",
                            "constraints": {"k_path_limit": 10, "interface_check": True}},
    "RUN_TESTS": {"action": "SYNTAX_VALIDATION", "source": "SANDBOX",
                   "constraints": {"run_unit_tests": True}},
    "TRACE_EXECUTION": {"action": "TRACE_EXECUTION", "source": "LOCAL_GRAPH",
                         "constraints": {"symbolic": True, "k_path_limit": 10}},
    "PATCH_FIX": {"action": "PATCH_FIX", "source": "FIX_ENGINE",
                   "constraints": {"minimal_change": True}},
    "VALIDATE_FIX": {"action": "SYMBOLIC_VALIDATION", "source": "SANDBOX",
                      "constraints": {"k_path_limit": 10, "verify_fix": True}},
    "CHECK_DEPENDENCIES": {"action": "CHECK_DEPENDENCIES", "source": "LOCAL_GRAPH",
                            "constraints": {"k_path_limit": 10}},
    "DELETE_AST_NODE": {"action": "DELETE_AST_NODE", "source": "LOCAL_GRAPH",
                         "constraints": {"cascade": True}},
    "VALIDATE_NO_BREAKAGE": {"action": "SYMBOLIC_VALIDATION", "source": "SANDBOX",
                              "constraints": {"k_path_limit": 10, "verify_no_breakage": True}},
    "BENCHMARK": {"action": "BENCHMARK", "source": "LOCAL_GRAPH",
                   "constraints": {"measure_performance": True}},
    "VALIDATE_PERFORMANCE": {"action": "SYNTAX_VALIDATION", "source": "SANDBOX",
                              "constraints": {"performance_check": True}},
    "QUALITY_REPORT": {"action": "QUALITY_REPORT", "source": "LOCAL_GRAPH",
                        "constraints": {"include_suggestions": True}},
    "SUGGEST_IMPROVEMENTS": {"action": "QUALITY_REPORT", "source": "LOCAL_GRAPH",
                              "constraints": {"include_suggestions": True}},
    "EXPLAIN_CODE": {"action": "EXPLAIN_CODE", "source": "LOCAL_GRAPH",
                      "constraints": {}},
    "GENERATE_DOCS": {"action": "EXPLAIN_CODE", "source": "LOCAL_GRAPH",
                       "constraints": {"generate_docs": True}},
    "SEARCH_DEFINITION": {"action": "SEARCH_DEFINITION", "source": "LOCAL_GRAPH",
                           "constraints": {}},
    "FIND_REFERENCES": {"action": "SEARCH_DEFINITION", "source": "LOCAL_GRAPH",
                         "constraints": {"find_references": True}},
    "QUICK_ANALYSIS": {"action": "QUICK_ANALYSIS", "source": "LOCAL_GRAPH",
                        "constraints": {}},
    "FULL_ANALYSIS": {"action": "FULL_ANALYSIS", "source": "LOCAL_GRAPH",
                       "constraints": {"deep": True}},
    "ANALYZE_AND_RESPOND": {"action": "ANALYZE_AND_RESPOND", "source": "LOCAL_GRAPH",
                             "constraints": {}},
    "SYNTAX_VALIDATION": {"action": "SYNTAX_VALIDATION", "source": "SANDBOX",
                           "constraints": {"basic": True}},
}


class StepsMixin:
    """Mixin providing plan step building and solver status determination."""

    def _build_steps(self, intent, routing, best_action_hint):
        """Construye los pasos del plan basado en la ruta y MCTS.

        The best_action_hint from MCTS is now used to:
        1. Detect if MCTS suggests an action not in the default step list
           and inject it as a high-priority step
        2. Reorder steps to prioritize MCTS-recommended actions
        3. Record the MCTS hint in step metadata
        """
        steps = []
        step_id = 1
        mcts_used = best_action_hint is not None

        if routing.route == RoutePath.SURGICAL_PATH:
            steps = self._build_surgical_steps(intent, step_id)
        elif routing.route == RoutePath.DEEP_PATH:
            steps = self._build_deep_steps(intent, step_id)
        else:  # FAST_PATH
            steps = self._build_fast_steps(intent, step_id)

        # === MCTS Integration: use best_action_hint to optimize plan ===
        if mcts_used and best_action_hint:
            steps = self._apply_mcts_hint(steps, best_action_hint, intent)

        return steps

    def _apply_mcts_hint(self, steps, best_action_hint, intent):
        """Apply MCTS hint to optimize step ordering and completeness.

        Strategy:
        1. If the MCTS-recommended action already exists in the plan,
           move it earlier (higher priority) and tag it with mcts_priority.
        2. If the MCTS-recommended action is NOT in the plan, insert it
           as a high-priority step (position 1, after initial analysis).
        3. Always tag the MCTS-recommended step with metadata.
        """
        action_info = _MCTS_ACTION_MAP.get(best_action_hint)
        if not action_info:
            # Unknown MCTS action — still record it but don't inject
            if steps:
                steps[0] = PlanStep(
                    step_id=steps[0].step_id,
                    action=steps[0].action,
                    target_node_name=steps[0].target_node_name,
                    source=steps[0].source,
                    constraints={
                        **steps[0].constraints,
                        "mcts_hint": best_action_hint,
                    },
                )
            return steps

        # Map MCTS action to the PlanStep action name
        mcts_step_action = action_info["action"]

        # Check if the MCTS-recommended action already exists in the plan
        existing_idx = None
        for i, step in enumerate(steps):
            if step.action == mcts_step_action:
                existing_idx = i
                break

        if existing_idx is not None:
            # Action exists — move it to position 1 (after initial analysis)
            # and tag with MCTS priority
            if existing_idx > 1:
                mcts_step = steps.pop(existing_idx)
                steps.insert(1, mcts_step)

            # Tag the MCTS-recommended step
            mcts_step = steps[1] if len(steps) > 1 else steps[0]
            steps[1] = PlanStep(
                step_id=mcts_step.step_id,
                action=mcts_step.action,
                target_node_name=mcts_step.target_node_name,
                source=mcts_step.source,
                constraints={
                    **mcts_step.constraints,
                    "mcts_priority": True,
                    "mcts_hint": best_action_hint,
                },
            )
        else:
            # Action NOT in the plan — insert it at position 1
            # (right after the initial analysis step)
            injected_step = PlanStep(
                step_id=0,  # Will be renumbered
                action=mcts_step_action,
                target_node_name=intent.target,
                source=action_info["source"],
                constraints={
                    **action_info["constraints"],
                    "mcts_priority": True,
                    "mcts_hint": best_action_hint,
                },
            )
            steps.insert(1, injected_step)

        # Renumber all steps
        for i, step in enumerate(steps):
            steps[i] = PlanStep(
                step_id=i + 1,
                action=step.action,
                target_node_name=step.target_node_name,
                source=step.source,
                constraints=step.constraints,
            )

        return steps

    def _build_surgical_steps(self, intent, step_id):
        """Build steps for SURGICAL_PATH route."""
        steps = []
        step_id = 1

        steps.append(PlanStep(step_id=step_id, action="ANALYZE_STRUCTURE",
            target_node_name=intent.target, source="LOCAL_GRAPH",
            constraints={"depth": "full", "include_metrics": True}))
        step_id += 1

        if intent.op == OperationType.CREATE:
            steps.append(PlanStep(step_id=step_id, action="SCRAPE_PATTERNS",
                target_node_name=intent.target, source="GITHUB_SCRAPE",
                constraints={"query": intent.scrap_query, "max_results": 3}))
            step_id += 1
            steps.append(PlanStep(step_id=step_id, action="GENERATE_CODE",
                target_node_name=intent.target, source="TEMPLATE_ENGINE",
                constraints={"require_validation": True, "security_check": True}))
            step_id += 1

        elif intent.op in [OperationType.REFACTOR, OperationType.OPTIMIZE]:
            steps.append(PlanStep(step_id=step_id, action="ANALYZE_PATTERNS",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"detect_smells": True, "metrics": True}))
            step_id += 1
            steps.append(PlanStep(step_id=step_id, action="REPLACE_AST_NODE",
                target_node_name=intent.target, source="SURGICAL_GRAPH",
                constraints={"preserve_interface": True, "security_check": True}))
            step_id += 1

        elif intent.op == OperationType.DEBUG:
            steps.append(PlanStep(step_id=step_id, action="TRACE_EXECUTION",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"symbolic": True, "k_path_limit": 10}))
            step_id += 1
            steps.append(PlanStep(step_id=step_id, action="PATCH_FIX",
                target_node_name=intent.target, source="FIX_ENGINE",
                constraints={"minimal_change": True}))
            step_id += 1

        elif intent.op == OperationType.DELETE:
            steps.append(PlanStep(step_id=step_id, action="CHECK_DEPENDENCIES",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"k_path_limit": 10}))
            step_id += 1
            steps.append(PlanStep(step_id=step_id, action="DELETE_AST_NODE",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"cascade": True}))
            step_id += 1

        else:
            steps.append(PlanStep(step_id=step_id, action="FULL_ANALYSIS",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"deep": True}))
            step_id += 1

        # Validacion simbolica obligatoria para ruta quirurgica
        steps.append(PlanStep(step_id=step_id, action="SYMBOLIC_VALIDATION",
            target_node_name=intent.target, source="SANDBOX",
            constraints={"k_path_limit": 10, "mock_externals": True}))

        return steps

    def _build_deep_steps(self, intent, step_id):
        """Build steps for DEEP_PATH route."""
        steps = []
        step_id = 1

        steps.append(PlanStep(step_id=step_id, action="ANALYZE_STRUCTURE",
            target_node_name=intent.target, source="LOCAL_GRAPH",
            constraints={"depth": "standard"}))
        step_id += 1

        if intent.op == OperationType.CREATE:
            steps.append(PlanStep(step_id=step_id, action="SCRAPE_PATTERNS",
                target_node_name=intent.target, source="GITHUB_SCRAPE",
                constraints={"query": intent.scrap_query, "max_results": 2}))
            step_id += 1
            steps.append(PlanStep(step_id=step_id, action="GENERATE_CODE",
                target_node_name=intent.target, source="TEMPLATE_ENGINE",
                constraints={"require_validation": True}))
            step_id += 1

        elif intent.op in [OperationType.REFACTOR, OperationType.OPTIMIZE]:
            steps.append(PlanStep(step_id=step_id, action="REPLACE_AST_NODE",
                target_node_name=intent.target, source="SURGICAL_GRAPH",
                constraints={"preserve_interface": True}))
            step_id += 1

        elif intent.op == OperationType.ANALYZE:
            steps.append(PlanStep(step_id=step_id, action="QUALITY_REPORT",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"include_suggestions": True}))
            step_id += 1

        elif intent.op == OperationType.DEBUG:
            steps.append(PlanStep(step_id=step_id, action="TRACE_EXECUTION",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"k_path_limit": 10}))
            step_id += 1

        else:
            steps.append(PlanStep(step_id=step_id, action="ANALYZE_AND_RESPOND",
                target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))
            step_id += 1

        steps.append(PlanStep(step_id=step_id, action="SYNTAX_VALIDATION",
            target_node_name=intent.target, source="SANDBOX",
            constraints={"basic": True}))

        return steps

    def _build_fast_steps(self, intent, step_id):
        """Build steps for FAST_PATH route."""
        steps = []
        step_id = 1

        steps.append(PlanStep(step_id=step_id, action="QUICK_ANALYSIS",
            target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))
        if intent.op == OperationType.EXPLAIN:
            steps.append(PlanStep(step_id=step_id+1, action="EXPLAIN_CODE",
                target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))
        elif intent.op == OperationType.SEARCH:
            steps.append(PlanStep(step_id=step_id+1, action="SEARCH_DEFINITION",
                target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))

        return steps

    def _determine_solver_status(self, solver_result, routing):
        """Determina el estado del solver basado en resultados reales."""
        if solver_result is None:
            if routing.route == RoutePath.FAST_PATH:
                return "SKIPPED_FAST_PATH"
            return "HEURISTIC_FALLBACK"

        status = solver_result.get("status", "UNKNOWN")

        if status in ("PROVEN", "SATISFIED"):
            return "PROVEN"
        elif status == "LIKELY_PROVEN":
            return "PROVEN_WITHIN_DEPTH_LIMIT"
        elif status == "TIMEOUT":
            return "TIMEOUT_SUBDIVIDE_REQUIRED"
        elif status in ("UNSATISFIABLE", "VIOLATED"):
            return "CONSTRAINTS_VIOLATED"
        elif status == "LIKELY_VIOLATED":
            return "LIKELY_VIOLATED"
        else:
            return "HEURISTIC_FALLBACK"
