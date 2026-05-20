"""simulation_engine — Core implementation (composed from mixins)."""

from __future__ import annotations

from ._mixin_core import SimulationEngineCoreMixin
from ._mixin_execution import SimulationEngineExecutionMixin


class SimulationEngine(SimulationEngineCoreMixin, SimulationEngineExecutionMixin):
    """Runs the entire DAG pipeline in simulation/dry-run mode.

    All results are in-memory only — no persistence of simulation
    results beyond the optional ``_simulation_history`` SQLite table
    (last 50 entries).

    Thread-safe: All public methods guarded by RLock.
    """


__all__ = ["SimulationEngine"]
