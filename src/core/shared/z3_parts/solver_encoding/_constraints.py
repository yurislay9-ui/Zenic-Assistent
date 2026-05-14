"""Z3 Solver Encoding — Constraint encoding helpers."""

import logging

from ._types import (
    _MAX_EXHAUSTIVE_PAIRS, _MAX_ENCODE_ENTRIES, _EVICT_BATCH_SIZE,
    _DEFAULT_MAX_SAMPLES, _REAL_DECIMAL_PRECISION,
)

try:
    import z3 as z3_module
    _HAS_Z3 = True
except ImportError:
    z3_module = None
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


class Z3ConstraintMixin:
    """Mixin for Z3 constraint encoding helpers."""

    # ================================================================
    #  Constraint encoding helpers
    # ================================================================

    def _add_enum_constraint(self, solver, z3_vars, var_meta, constraint):
        """
        Add a constraint between Enum/Mixed variables as native Z3
        equality expressions.
        """
        meta1 = var_meta.get(constraint.var1, {})
        meta2 = var_meta.get(constraint.var2, {})
        const_map1 = meta1.get("const_map", {})
        const_map2 = meta2.get("const_map", {})

        valid_pairs = []
        for v1 in meta1.get("values", []):
            for v2 in meta2.get("values", []):
                try:
                    if constraint.satisfied(v1, v2):
                        key1 = str(v1)
                        key2 = str(v2)
                        z3_const1 = const_map1.get(key1) if key1 in const_map1 else const_map1.get(v1)
                        z3_const2 = const_map2.get(key2) if key2 in const_map2 else const_map2.get(v2)
                        if z3_const1 is not None and z3_const2 is not None:
                            valid_pairs.append(
                                z3_module.And(
                                    z3_vars[constraint.var1] == z3_const1,
                                    z3_vars[constraint.var2] == z3_const2,
                                )
                            )
                except Exception as e:
                    logger.debug("Z3Solver: Enum constraint pair failed: %s", e)
                    continue

        if valid_pairs:
            solver.add(z3_module.Or(*valid_pairs))
        else:
            solver.add(z3_module.BoolVal(False))

    def _add_numeric_constraint(self, solver, z3_vars, constraint, num_type="int",
                                 var_meta=None):
        """
        Add a constraint between numeric variables using native
        Z3 arithmetic/comparison expressions.
        """
        v1 = z3_vars[constraint.var1]
        v2 = z3_vars[constraint.var2]

        desc = constraint.description.lower()

        if "not_equal" in desc or "!=" in desc or "not equal" in desc:
            solver.add(v1 != v2)
            return

        if "less_than" in desc or " < " in desc:
            solver.add(v1 < v2)
            return

        if "greater_than" in desc or " > " in desc:
            solver.add(v1 > v2)
            return

        if "less_or_equal" in desc or "<=" in desc:
            solver.add(v1 <= v2)
            return

        if "greater_or_equal" in desc or ">=" in desc:
            solver.add(v1 >= v2)
            return

        if "equal" in desc and "not_equal" not in desc:
            solver.add(v1 == v2)
            return

        # FIXED FALLBACK: Domain-aware constraint encoding
        if var_meta is not None:
            meta1 = var_meta.get(constraint.var1, {})
            meta2 = var_meta.get(constraint.var2, {})
            vals1 = meta1.get("values", [])
            vals2 = meta2.get("values", [])

            if vals1 and vals2:
                total_pairs = len(vals1) * len(vals2)

                if total_pairs <= _MAX_EXHAUSTIVE_PAIRS:
                    valid_conditions = []
                    for val1 in vals1:
                        for val2 in vals2:
                            try:
                                if constraint.satisfied(val1, val2):
                                    cond1 = (v1 == val1) if num_type == "int" else (v1 == z3_module.RealVal(str(val1)))
                                    cond2 = (v2 == val2) if num_type == "int" else (v2 == z3_module.RealVal(str(val2)))
                                    valid_conditions.append(z3_module.And(cond1, cond2))
                            except Exception:
                                continue

                    if valid_conditions:
                        solver.add(z3_module.Or(*valid_conditions))
                    else:
                        solver.add(z3_module.BoolVal(False))
                        logger.debug(
                            "Numeric constraint '%s': no valid pairs found — adding False",
                            constraint.description
                        )
                    return
                else:
                    sample1 = self._sample_numeric_domain(vals1, max_samples=_DEFAULT_MAX_SAMPLES)
                    sample2 = self._sample_numeric_domain(vals2, max_samples=_DEFAULT_MAX_SAMPLES)

                    valid_conditions = []
                    for val1 in sample1:
                        for val2 in sample2:
                            try:
                                if constraint.satisfied(val1, val2):
                                    cond1 = (v1 == val1) if num_type == "int" else (v1 == z3_module.RealVal(str(val1)))
                                    cond2 = (v2 == val2) if num_type == "int" else (v2 == z3_module.RealVal(str(val2)))
                                    valid_conditions.append(z3_module.And(cond1, cond2))
                            except Exception:
                                continue

                    if valid_conditions:
                        solver.add(z3_module.Or(*valid_conditions))
                        logger.debug(
                            "Numeric constraint '%s': sampled %d/%d pairs, found %d valid",
                            constraint.description,
                            len(sample1) * len(sample2),
                            total_pairs,
                            len(valid_conditions),
                        )
                    else:
                        solver.add(z3_module.BoolVal(False))
                    return

        logger.warning(
            "Numeric constraint '%s' has no domain info — adding equality fallback.",
            constraint.description
        )
        solver.add(v1 == v2)

    def _sample_numeric_domain(self, values, max_samples=_DEFAULT_MAX_SAMPLES):
        """Sample representative values from a numeric domain for constraint testing."""
        if len(values) <= max_samples:
            return list(values)

        sorted_vals = sorted(set(v for v in values if isinstance(v, (int, float))))
        if not sorted_vals:
            return values[:max_samples]

        if len(sorted_vals) <= max_samples:
            return sorted_vals

        step = (len(sorted_vals) - 1) / (max_samples - 1)
        indices = [int(round(i * step)) for i in range(max_samples)]
        indices = sorted(set(max(0, min(i, len(sorted_vals) - 1)) for i in indices))

        return [sorted_vals[i] for i in indices]

    def _add_boolean_constraint(self, solver, z3_vars, constraint):
        """Add a constraint between boolean variables using Z3 logical operators."""
        v1 = z3_vars[constraint.var1]
        v2 = z3_vars[constraint.var2]
        desc = constraint.description.lower()

        if "implies" in desc or "requires" in desc:
            solver.add(z3_module.Implies(v1, v2))
            return

        if "exclu" in desc or "mutual" in desc:
            solver.add(z3_module.Not(z3_module.And(v1, v2)))
            return

        if "equivalent" in desc or "iff" in desc or "same" in desc:
            solver.add(v1 == v2)
            return

        for v1_val in [True, False]:
            for v2_val in [True, False]:
                if not constraint.satisfied(v1_val, v2_val):
                    if v1_val and v2_val:
                        solver.add(z3_module.Not(z3_module.And(v1, v2)))
                    elif v1_val and not v2_val:
                        solver.add(z3_module.Not(z3_module.And(v1, z3_module.Not(v2))))
                    elif not v1_val and v2_val:
                        solver.add(z3_module.Not(z3_module.And(z3_module.Not(v1), v2)))
                    else:
                        solver.add(z3_module.Not(z3_module.And(z3_module.Not(v1), z3_module.Not(v2))))

    # ================================================================
    #  Encoding helpers - Bijective mapping
    # ================================================================

    def _reset_encoding(self):
        """Clear bijective encoding maps to prevent unbounded memory growth."""
        self._encode_map = {}
        self._decode_map = {}
        self._next_encode_id = 0

    def _encode_value(self, value):
        """Bijective encoding of domain values to unique sequential integers."""
        if len(self._encode_map) >= _MAX_ENCODE_ENTRIES:
            keys_to_evict = list(self._encode_map.keys())[:_EVICT_BATCH_SIZE]
            for k in keys_to_evict:
                eid = self._encode_map.pop(k, None)
                if eid is not None:
                    self._decode_map.pop(eid, None)
            logger.debug(
                "Z3Solver: Encoding map evicted %d entries (limit: %d)",
                len(keys_to_evict), _MAX_ENCODE_ENTRIES
            )

        try:
            key = (type(value).__name__, value)
            hash(key)
        except TypeError:
            key = (type(value).__name__, repr(value))

        if key not in self._encode_map:
            self._encode_map[key] = self._next_encode_id
            self._decode_map[self._next_encode_id] = value
            self._next_encode_id += 1

        return self._encode_map[key]

    def _decode_value(self, z3_value, domain):
        """Decode a Z3 integer value back to the original domain value."""
        try:
            int_val = z3_value.as_long()
            if int_val in self._decode_map:
                return self._decode_map[int_val]
            for v in domain:
                if self._encode_value(v) == int_val:
                    return v
        except Exception as decode_err:
            logger.debug(f"Z3Solver: Domain lookup failed: {decode_err}")
        return str(z3_value)
