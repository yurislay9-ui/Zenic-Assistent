"""Mixin: Solver methods for APAPlanner.

FIX (Phase 2): Added retry with exponential backoff for solver execution.
Solvers can fail transiently (OOM, resource contention, Z3 internal errors)
and retrying once often succeeds. Retry is only for ERROR results, not TIMEOUT
(since timeout means the budget was exhausted legitimately).
"""

import gc
import time
import logging

from ._imports import (
    logger, HAS_Z3, Z3Solver, TimeoutEnforcer,
    CodeConstraintBuilder, Constraint, get_governor
)

# Retry configuration for solver execution
_SOLVER_MAX_ATTEMPTS = 2  # 1 initial + 1 retry
_SOLVER_RETRY_DELAY = 0.5  # seconds (exponential backoff base)


class SolverMixin:
    """Mixin providing SMT and fast solver execution."""

    def _run_smt_solver(self, intent, timeout_ms=None):
        """
        Ejecuta el SMT Solver (Z3 si disponible, AC-3 si no) para nodos quirurgicos.

        Verifica invariantes de codigo con timeout adaptativo.
        Implementa el Protocolo Abortivo del documento:
        si el solver hace timeout, devuelve TIMEOUT para que el
        orquestador subdivida automaticamente.

        Incluye proteccion de recursos:
        - Timeout adaptativo segun carga del sistema
        - GC forzado despues de Z3 (libera memoria del solver)
        - Retry with exponential backoff on transient errors
        """
        solver_type = "Z3" if HAS_Z3 else "AC-3"
        effective_timeout = timeout_ms or self.solver_timeout_ms
        governor = get_governor()

        logger.info("Running %s solver for surgical node: %s (timeout: %dms)",
                     solver_type, intent.target, effective_timeout)

        last_error_result = None
        for attempt in range(1, _SOLVER_MAX_ATTEMPTS + 1):
            try:
                # Crear el solver apropiado con timeout adaptativo
                z3_solver = Z3Solver(timeout_ms=effective_timeout)

                # Construir dominios y restricciones desde el analisis
                domains = CodeConstraintBuilder.build_domains_from_code({})

                # Agregar dominios especificos del target quirurgico
                domains["target_type"] = ["critical", "standard", "unknown"]
                domains["mutation_risk"] = ["high", "medium", "low", "none"]
                domains["validation_needed"] = ["full", "partial", "none"]

                # Restriccion critica: si es target critico, requiere validacion completa
                constraints = CodeConstraintBuilder.build_null_safety_constraints([
                    {"name": "target_type", "can_be_none": False},
                    {"name": "mutation_risk", "can_be_none": False},
                    {"name": "validation_needed", "can_be_none": False}
                ])

                constraints.append(Constraint(
                    "target_type", "validation_needed",
                    lambda t, v: t != "critical" or v == "full",
                    description="critical_targets_require_full_validation"
                ))

                constraints.append(Constraint(
                    "mutation_risk", "validation_needed",
                    lambda r, v: r != "high" or v in ["full", "partial"],
                    description="high_risk_requires_validation"
                ))

                # Ejecutar con timeout enforcement real
                enforcer = TimeoutEnforcer(timeout_ms=effective_timeout)
                result, timed_out = enforcer.execute_with_timeout(
                    z3_solver.solve_constraints, domains, constraints
                )

                # GC forzado despues de solver pesado (Z3 puede dejar mucha basura)
                gc.collect(1)

                if timed_out:
                    logger.warning(
                        "SMT Solver TIMEOUT (%d ms) para %s - Protocolo Abortivo activado",
                        effective_timeout, intent.target
                    )
                    return {
                        "status": "TIMEOUT",
                        "assignment": None,
                        "solver_type": solver_type,
                        "timeout_ms": effective_timeout,
                        "subdivide_required": True,  # Senal para el Protocolo Abortivo
                    }

                # Agregar metadata del solver usado
                if isinstance(result, dict):
                    result["solver_type"] = solver_type
                    if attempt > 1:
                        result["retries"] = attempt - 1

                return result

            except Exception as e:
                delay = _SOLVER_RETRY_DELAY * (2 ** (attempt - 1))
                logger.error(
                    "SMT Solver error (attempt %d/%d): %s%s",
                    attempt, _SOLVER_MAX_ATTEMPTS, e,
                    f" — retrying in {delay:.1f}s" if attempt < _SOLVER_MAX_ATTEMPTS else ""
                )
                # GC de emergencia
                gc.collect(2)
                last_error_result = {
                    "status": "ERROR",
                    "message": str(e),
                    "solver_type": solver_type,
                    "subdivide_required": True,
                }
                if attempt < _SOLVER_MAX_ATTEMPTS:
                    time.sleep(delay)

        return last_error_result

    def _run_fast_solver(self, intent):
        """
        Ejecuta un solver rapido (5s timeout) para nodos moderados.
        Solo verifica invariantes basicas.

        Incluye timeout enforcement real como _run_smt_solver.
        Retry with exponential backoff on transient errors.
        """
        last_error_result = None
        for attempt in range(1, _SOLVER_MAX_ATTEMPTS + 1):
            try:
                domains = {
                    "target_type": ["standard", "unknown"],
                    "mutation_risk": ["medium", "low", "none"],
                    "validation_needed": ["partial", "none"]
                }

                constraints = [
                    Constraint(
                        "mutation_risk", "validation_needed",
                        lambda r, v: r != "medium" or v != "none",
                        description="medium_risk_needs_some_validation"
                    )
                ]

                # Usar Z3Solver (que internamente usa Z3 o AC-3)
                z3_solver = Z3Solver(timeout_ms=self.solver_fast_timeout_ms)

                # Ejecutar con timeout enforcement real
                enforcer = TimeoutEnforcer(timeout_ms=self.solver_fast_timeout_ms)
                result, timed_out = enforcer.execute_with_timeout(
                    z3_solver.solve_constraints, domains, constraints
                )

                if timed_out:
                    logger.warning(
                        "Fast Solver TIMEOUT (%d ms) para %s",
                        self.solver_fast_timeout_ms, intent.target
                    )
                    return {
                        "status": "TIMEOUT",
                        "assignment": None,
                        "timeout_ms": self.solver_fast_timeout_ms,
                    }

                if isinstance(result, dict) and attempt > 1:
                    result["retries"] = attempt - 1

                return result

            except Exception as e:
                delay = _SOLVER_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Fast solver error (attempt %d/%d): %s%s",
                    attempt, _SOLVER_MAX_ATTEMPTS, e,
                    f" — retrying in {delay:.1f}s" if attempt < _SOLVER_MAX_ATTEMPTS else ""
                )
                last_error_result = {"status": "ERROR", "message": str(e)}
                if attempt < _SOLVER_MAX_ATTEMPTS:
                    time.sleep(delay)

        return last_error_result
