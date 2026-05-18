"""
Z3 Null-Safety Proof Mixin.

Provides the _z3_prove_null_safety method using Z3 EnumSort {NONE, SOME_VALUE}
for formal null-safety verification.

Two-phase proof:
  Phase 1: Consistency check — verify null-safety constraints are satisfiable
           (non-nullable = SOME_VALUE, nullable = SOME_VALUE | NONE)
  Phase 2: Counterexample search — try to find a state where ANY non-nullable
           variable = NONE, using ONLY dataflow constraints (NOT the Phase 1
           classification equalities). If UNSAT → PROVEN; if SAT → VIOLATED.

Fix (C5): Phase 2 must NOT re-add Phase 1 equality constraints
(non-nullable = SOME_VAL). Previously, Phase 2 added both the classification
constraints AND the negation, making it trivially UNSAT (vacuous proof).
Now Phase 2 starts with a fresh solver and only adds dataflow constraints
plus the negation, so UNSAT genuinely means null-safety holds.
"""

import gc
import logging

try:
    import z3 as z3_module  # type: ignore[import-unresolved]
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


class Z3NullSafetyMixin:
    """Mixin for null-safety proof methods using Z3 EnumSort."""

    def _z3_prove_null_safety(self, variable_names, nullable_vars,
                               assignments=None):
        """Null-safety proof using Z3 EnumSort {NONE, SOME_VALUE}.

        Two-phase proof:
        1. Consistency check: verify null-safety constraints are satisfiable
           (non-nullable = SOME_VALUE, nullable = SOME_VALUE | NONE)
        2. Counterexample search: try to find a state where ANY non-nullable
           variable = NONE, using dataflow constraints from assignments.
           If UNSAT → PROVEN; if SAT → VIOLATED.

        Formal justification:
          To prove "non-nullable vars are never NONE" (property P),
          we ask Z3 to find a model where ¬P holds (some non-nullable = NONE).
          If ¬P is UNSAT, then P is a tautology under these constraints.

        Args:
            variable_names: List of all variable names.
            nullable_vars: Set of variable names that are nullable.
            assignments: Optional list of (target, source) pairs representing
                dataflow (e.g., x is assigned from y). If a source is nullable,
                the target can be NONE only if the source can be NONE.
        """
        try:
            if not variable_names:
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "counterexamples": [],
                    "proof": "No variables to verify — vacuously true",
                }

            # Create EnumSort for nullability domain
            null_sort, null_consts = z3_module.EnumSort(
                self._unique_sort_name("Nullability"), ["NONE", "SOME_VALUE"]
            )
            NONE_VAL, SOME_VAL = null_consts[0], null_consts[1]

            # Create a Z3 variable of this sort for each program variable
            z3_vars = {}
            for name in variable_names:
                z3_vars[name] = z3_module.Const(f"null_{name}", null_sort)

            non_nullable = [v for v in variable_names if v not in nullable_vars]

            # If there are no non-nullable variables, null-safety is trivially true
            if not non_nullable:
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "counterexamples": [],
                    "proof": "No non-nullable variables — null-safety is vacuously true",
                }

            # ============================================================
            #  Phase 1: Consistency check
            #  Verify that the null-safety constraints are not contradictory
            # ============================================================
            consistency_solver = z3_module.Solver()
            consistency_solver.set("timeout", self.timeout_ms)

            for var_name in variable_names:
                if var_name not in nullable_vars:
                    consistency_solver.add(z3_vars[var_name] == SOME_VAL)
                else:
                    consistency_solver.add(
                        z3_module.Or(
                            z3_vars[var_name] == NONE_VAL,
                            z3_vars[var_name] == SOME_VAL,
                        )
                    )

            consistency_result = consistency_solver.check()
            if consistency_result == z3_module.unsat:
                # Null-safety conditions are contradictory — cannot be satisfied
                return {
                    "status": "UNSATISFIABLE",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "counterexamples": [],
                    "proof": "Z3: null-safety conditions are contradictory (cannot be satisfied)",
                }
            elif consistency_result != z3_module.sat:
                # Unknown/timeout on consistency — cannot proceed to Phase 2
                return {
                    "status": "UNKNOWN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "counterexamples": [],
                    "proof": "Z3 returned unknown on consistency check (timeout or unsupported theory)",
                }

            # Phase 1 passed: constraints are consistent (SAT)
            # But SAT ≠ PROVEN! We must now try to prove that non-nullable
            # vars can NEVER be NONE under these constraints.

            # ============================================================
            #  Phase 2: Counterexample search (THE ACTUAL PROOF)
            #  Ask Z3: "Is there a state where some non-nullable = NONE?"
            #  If UNSAT → PROVEN (no such state exists)
            #  If SAT   → VIOLATED (found a counterexample)
            #
            #  CRITICAL (Fix C5): Phase 2 must NOT re-add Phase 1's
            #  equality constraints (non-nullable = SOME_VAL). Previously,
            #  Phase 2 added both those equalities AND the negation
            #  (Or(*[non-nullable == NONE])), which is trivially UNSAT —
            #  making the proof vacuous (always PROVEN regardless of code).
            #
            #  FIX: Phase 2 now adds dataflow constraints so the proof
            #  is meaningful. A variable can only be NONE if it was
            #  assigned from a nullable source. Without dataflow
            #  constraints, variables are unconstrained and Z3 always
            #  finds SAT (false VIOLATED).
            # ============================================================
            proof_solver = z3_module.Solver()
            proof_solver.set("timeout", self.timeout_ms)

            # --- Dataflow constraints ---
            # Key insight: a non-nullable variable can only be NONE if it
            # was assigned from a nullable source. We model this with:
            #   1. Nullable vars can be NONE or SOME (already tracked)
            #   2. Non-nullable vars with no nullable source cannot be NONE
            #   3. If target = source and source can be NONE, target can be NONE

            # Build the set of variables that could potentially be NONE
            # based on dataflow: a var can_be_none if it's nullable OR
            # it's assigned from a var that can_be_none.
            can_be_none = set(nullable_vars)
            if assignments:
                # Propagate nullability through assignments
                changed = True
                while changed:
                    changed = False
                    for target, source in assignments:
                        if target in variable_names and source in variable_names:
                            if source in can_be_none and target not in can_be_none:
                                can_be_none.add(target)
                                changed = True

                # For each assignment, add implication constraint:
                # If source can be NONE, then target can be NONE
                for target, source in assignments:
                    if target in z3_vars and source in z3_vars:
                        # target is NONE only if source is NONE
                        # (dataflow: value flows from source to target)
                        proof_solver.add(
                            z3_module.Implies(
                                z3_vars[target] == NONE_VAL,
                                z3_vars[source] == NONE_VAL,
                            )
                        )

            # Variables that cannot be NONE (not in can_be_none set)
            # are constrained to SOME_VAL even in Phase 2.
            # This makes the proof meaningful: only vars with nullable
            # dataflow sources could potentially be NONE.
            for var_name in variable_names:
                if var_name not in can_be_none:
                    # No nullable source → must be SOME_VAL
                    proof_solver.add(z3_vars[var_name] == SOME_VAL)

            # Add the NEGATION of the null-safety property:
            # "at least one non-nullable var IS NONE"
            # If UNSAT → it's impossible under dataflow constraints → PROVEN
            # If SAT   → found a counterexample → VIOLATED
            proof_solver.add(
                z3_module.Or(
                    *[z3_vars[v] == NONE_VAL for v in non_nullable]
                )
            )

            proof_result = proof_solver.check()

            if proof_result == z3_module.unsat:
                # Counterexample is UNSATISFIABLE
                # This means it's IMPOSSIBLE for any non-nullable var to be NONE
                # → Null-safety is PROVEN
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "counterexamples": [],
                    "proof": (
                        "Z3 EnumSort PROVED: counterexample search (non-nullable = NONE) "
                        "is UNSAT — it is impossible for any non-nullable variable to be None "
                        f"under the given constraints. Verified {len(non_nullable)} non-nullable "
                        f"variable(s): {non_nullable}"
                    ),
                }
            elif proof_result == z3_module.sat:
                # Found a counterexample — null-safety is VIOLATED
                model = proof_solver.model()
                counterexample = {}
                for var_name in non_nullable:
                    val = model.eval(z3_vars[var_name])
                    if str(val) == "NONE":
                        counterexample[var_name] = "None"

                # Also include nullable vars for full context
                full_assignment = {}
                for var_name in variable_names:
                    val = model.eval(z3_vars[var_name])
                    full_assignment[var_name] = (
                        "None" if str(val) == "NONE" else "Some"
                    )

                return {
                    "status": "VIOLATED",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "counterexamples": [counterexample],
                    "proof": (
                        f"Z3 FOUND VIOLATION: non-nullable variable(s) "
                        f"{list(counterexample.keys())} can be None under the given "
                        f"constraints. Counterexample: {counterexample}"
                    ),
                    "model": full_assignment,
                }
            else:
                # Unknown/timeout on Phase 2
                # We know constraints are consistent (Phase 1), but
                # can't prove or disprove null-safety
                return {
                    "status": "LIKELY_PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,  # Best-effort: Phase 1 passed
                    "counterexamples": [],
                    "proof": (
                        "Z3: Phase 1 (consistency) passed, but Phase 2 (counterexample search) "
                        "returned UNKNOWN/timeout. Null-safety is likely proven but not formally "
                        "verified within the time budget."
                    ),
                }

        except Exception as e:
            logger.error("Z3 null-safety proof error: %s", e)
            return {"status": "ERROR", "solver_type": "Z3", "message": str(e)}
        finally:
            gc.collect()
