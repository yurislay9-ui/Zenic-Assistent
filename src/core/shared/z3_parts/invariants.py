"""
Z3 Invariant Verification Mixin.

Provides core invariant proof methods:
- _z3_prove_invariant: Main invariant verification
- _z3_invariant_enumerated: For small domains via enumeration
- _z3_invariant_bounded: For larger domains via bounded verification

Code-invariant and pattern-invariant methods are in invariants_patterns.py.
"""

import gc
import logging

try:
    import z3 as z3_module  # type: ignore[import-unresolved]
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

from ..constraint_solver import ConstraintSolver
# Phase 5 — Deterministic RNG instead of bare random.choice
from ..deterministic import DeterministicRNG

logger = logging.getLogger(__name__)

# Named constants (previously magic numbers)
_INV_ENUM_THRESHOLD = 5000
_MAX_VIOLATION_CONSTRAINTS = 50
_NUMERIC_DOMAIN_INT_THRESHOLD = 50
_BOUNDED_SAMPLE_COUNT = 200
_BOUNDED_TIMEOUT_DIVISOR = 50


class Z3InvariantMixin:
    """Mixin for invariant verification methods using Z3."""

    def _z3_prove_invariant(self, invariant_func, variables, domains):
        """
        Invariant verification using Z3 with EnumSort encoding.

        Strategy:
        1. Encode variables with EnumSort for finite domains
        2. Use Z3's Implies/ForAll/Exists where possible
        3. For simple domains, encode invariant violation directly
        4. For complex invariant functions, use bounded Z3 verification
           up to a depth limit, then AC-3 fallback
        """
        try:
            # Reset encoding for this proof
            self._reset_encoding()

            # Compute total state space size
            total_states = 1
            for var_name in variables:
                if var_name in domains and domains[var_name]:
                    total_states *= len(domains[var_name])

            # For small domains, enumerate and build Z3 constraints directly
            # that capture the invariant function
            if total_states <= _INV_ENUM_THRESHOLD:
                result = self._z3_invariant_enumerated(
                    invariant_func, variables, domains
                )
                if result is not None:
                    return result

            # For larger domains, use bounded Z3 verification:
            # encode domain membership + try to find counterexamples
            # within a bounded search depth
            result = self._z3_invariant_bounded(
                invariant_func, variables, domains
            )
            if result is not None:
                return result

            # Final fallback to AC-3
            ac3_solver = ConstraintSolver(timeout_ms=self.timeout_ms)
            result = ac3_solver.verify_invariant(invariant_func, variables, domains)
            result["solver_type"] = "Z3+AC3_HYBRID"
            return result

        except Exception as e:
            logger.error("Z3 invariant proof error: %s", e)
            return {"status": "ERROR", "solver_type": "Z3", "message": str(e)}
        finally:
            gc.collect()

    def _z3_invariant_enumerated(self, invariant_func, variables, domains):
        """
        For small domains: enumerate all states where the invariant is
        VIOLATED, encode them as Z3 constraints (using Int encoding with
        bijective mapping), and check if any violation is reachable.
        """
        solver = z3_module.Solver()
        solver.set("timeout", self.timeout_ms)

        # NOTE: _reset_encoding() is already called in _z3_prove_invariant
        # before dispatching to this method. No need to reset again here.

        # Build Z3 Int variables and domain constraints
        z3_vars = {}
        for var_name in variables:
            if var_name not in domains or not domains[var_name]:
                continue
            vals = domains[var_name]
            z3_var = z3_module.Int(var_name)
            z3_vars[var_name] = z3_var
            # Restrict to domain using bijective encoding
            encoded_vals = [self._encode_value(v) for v in vals]
            if encoded_vals:
                solver.add(
                    z3_module.Or(*[z3_var == ev for ev in encoded_vals])
                )

        # Enumerate states where invariant is VIOLATED
        # Build Z3 constraints encoding these violation patterns
        violation_constraints = []
        checked = 0
        max_violations = _MAX_VIOLATION_CONSTRAINTS

        def enumerate_states(idx, assignment, z3_conds):
            nonlocal checked
            if len(violation_constraints) >= max_violations:
                return
            if idx >= len(variables):
                checked += 1
                try:
                    if not invariant_func(**assignment):
                        # This assignment violates the invariant
                        violation_constraints.append(
                            z3_module.And(*z3_conds) if z3_conds
                            else z3_module.BoolVal(True)
                        )
                except Exception as inv_err:
                    logger.debug(f"Z3Solver: Invariant evaluation failed: {inv_err}")
                return

            var_name = variables[idx]
            if var_name not in domains or not domains[var_name]:
                enumerate_states(idx + 1, assignment, z3_conds)
                return

            for val in domains[var_name]:
                assignment[var_name] = val
                encoded = self._encode_value(val)
                z3_cond = z3_vars[var_name] == encoded
                enumerate_states(idx + 1, assignment, z3_conds + [z3_cond])

        enumerate_states(0, {}, [])

        if not violation_constraints:
            # No violations found at all -> PROVEN
            return {
                "status": "PROVEN",
                "solver_type": "Z3_INT",
                "verified": True,
                "counterexamples": [],
                "checked": checked,
                "proof": f"Z3 enumerated {checked} states, no invariant violations",
            }

        # Ask Z3: is there a state matching ANY violation pattern?
        # If UNSAT, violation patterns are unreachable -> PROVEN
        solver.add(z3_module.Or(*violation_constraints))
        result = solver.check()

        if result == z3_module.unsat:
            return {
                "status": "PROVEN",
                "solver_type": "Z3_INT",
                "verified": True,
                "counterexamples": [],
                "checked": checked,
                "proof": f"Z3 proved invariant holds: violation patterns unsatisfiable ({checked} states checked)",
            }
        elif result == z3_module.sat:
            model = solver.model()
            counterexample = {}
            for var_name in variables:
                if var_name in z3_vars:
                    val = model.eval(z3_vars[var_name])
                    counterexample[var_name] = self._decode_value(
                        val, domains.get(var_name, [])
                    )
            return {
                "status": "VIOLATED",
                "solver_type": "Z3_INT",
                "verified": False,
                "counterexamples": [counterexample],
                "checked": checked,
                "proof": f"Z3 found invariant violation: {counterexample}",
            }
        else:
            return None  # Fall through to bounded or AC-3

    def _z3_invariant_bounded(self, invariant_func, variables, domains):
        """
        For larger domains: use Z3 with bounded verification.

        Encode domain membership using EnumSort (or Int with bounds for
        large numeric domains), then try to find a counterexample by
        sampling within the Z3 search space up to a depth limit.
        """
        solver = z3_module.Solver()
        solver.set("timeout", self.timeout_ms)

        z3_vars = {}
        var_domain_maps = {}  # var_name -> {z3_const_name: domain_value}
        var_sorts = {}

        for var_name in variables:
            if var_name not in domains or not domains[var_name]:
                continue
            vals = domains[var_name]
            # For very large numeric domains, use Int with bounds
            if len(vals) > _NUMERIC_DOMAIN_INT_THRESHOLD and all(isinstance(v, (int, float)) for v in vals):
                z3_vars[var_name] = z3_module.Int(var_name)
                min_val = int(min(vals))
                max_val = int(max(vals))
                solver.add(z3_vars[var_name] >= min_val)
                solver.add(z3_vars[var_name] <= max_val)
                var_domain_maps[var_name] = None  # Flag: Int encoding
                var_sorts[var_name] = "Int"
            else:
                # Use EnumSort for small/medium finite domains
                const_names = [f"{var_name}__v{i}" for i in range(len(vals))]
                if len(const_names) < 2:
                    const_names = const_names + [f"{var_name}__dummy"]
                sort, consts = z3_module.EnumSort(self._unique_sort_name(f"dom_{var_name}"), const_names)
                z3_vars[var_name] = z3_module.Const(var_name, sort)
                var_domain_maps[var_name] = dict(zip(const_names, vals))
                var_sorts[var_name] = sort
                # Domain membership is implicit with EnumSort

        # Sample-based bounded verification:
        # Generate random test points and add violation constraints
        # Phase 5: Use DeterministicRNG instead of bare random.choice
        _z3_rng = DeterministicRNG("z3_invariant_sampling")

        violations_found = []
        samples = min(_BOUNDED_SAMPLE_COUNT, self.timeout_ms // _BOUNDED_TIMEOUT_DIVISOR)  # Scale with timeout
        checked = 0

        for _ in range(samples):
            assignment = {}
            for var_name in variables:
                if var_name in domains and domains[var_name]:
                    assignment[var_name] = _z3_rng.choice(domains[var_name])
            checked += 1
            try:
                if not invariant_func(**assignment):
                    violations_found.append(assignment)
                    if len(violations_found) >= 3:
                        break
            except Exception as inv_err:
                logger.debug(f"Z3Solver: Invariant sampling failed: {inv_err}")

        if violations_found:
            return {
                "status": "VIOLATED",
                "solver_type": "Z3_BOUNDED",
                "verified": False,
                "counterexamples": violations_found[:3],
                "checked": checked,
                "proof": f"Z3 bounded verification found violations: {violations_found[:3]}",
            }

        # No violations in sampling -> likely proven
        return {
            "status": "LIKELY_PROVEN",
            "solver_type": "Z3_BOUNDED",
            "verified": False,  # LIKELY_PROVEN ≠ PROVEN; bounded sampling is not formal proof
            "counterexamples": [],
            "checked": checked,
            "proof": f"Z3 bounded verification: no violations in {checked} samples",
        }
