"""
ZENIC-AGENTS - Behavioral Pattern: State Machine

Thread-safe finite state machine with entry/exit callbacks,
transition guards, and transition history.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ======================================================================
# Data classes
# ======================================================================

@dataclass
class State:
    """
    Representation of a single state in the machine.

    Attributes:
        name: Unique state identifier.
        on_enter: Optional callback invoked when this state is entered.
                  Signature: ``on_enter(from_state: str) -> None``
        on_exit: Optional callback invoked when this state is exited.
                 Signature: ``on_exit(to_state: str) -> None``
        allowed_transitions: List of state names this state can transition to.
    """
    name: str
    on_enter: Optional[Callable[[str], None]] = None
    on_exit: Optional[Callable[[str], None]] = None
    allowed_transitions: List[str] = field(default_factory=list)


@dataclass
class Transition:
    """
    Representation of a transition between two states.

    Attributes:
        from_state: Source state name.
        to_state: Target state name.
        condition: Optional guard — return True to allow the transition.
                   Signature: ``condition() -> bool``
        action: Optional action executed when the transition fires.
                Signature: ``action() -> None``
    """
    from_state: str
    to_state: str
    condition: Optional[Callable[[], bool]] = None
    action: Optional[Callable[[], None]] = None


# ======================================================================
# State Machine
# ======================================================================

class StateMachine:
    """
    Thread-safe finite state machine.

    Usage::

        states = {
            "idle": State("idle", allowed_transitions=["running", "error"]),
            "running": State("running", allowed_transitions=["paused", "done", "error"],
                             on_enter=lambda f: print(f"Entered running from {f}")),
            "paused": State("paused", allowed_transitions=["running", "error"]),
            "done": State("done", allowed_transitions=["idle"]),
            "error": State("error", allowed_transitions=["idle"]),
        }
        transitions = [
            Transition("idle", "running"),
            Transition("running", "paused"),
            Transition("paused", "running"),
            Transition("running", "done"),
            Transition("running", "error"),
            Transition("error", "idle"),
            Transition("done", "idle"),
        ]
        sm = StateMachine("idle", transitions, states)
        sm.transition("running")  # True
        sm.current_state           # "running"
        sm.can_transition("paused")  # True
    """

    def __init__(
        self,
        initial_state: str,
        transitions: List[Transition],
        states: Optional[Dict[str, State]] = None,
    ) -> None:
        """
        Args:
            initial_state: Name of the starting state.
            transitions: List of allowed transitions.
            states: Optional dict of state name → :class:`State`.  If not
                    provided, states are inferred from transitions with
                    empty ``allowed_transitions``.

        Raises:
            ValueError: If *initial_state* is not in the states dict.
        """
        self._states: Dict[str, State] = dict(states) if states else {}
        self._transitions: List[Transition] = list(transitions)
        self._initial_state = initial_state
        self._current_state = initial_state
        self._history: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

        # Infer states from transitions if not explicitly provided
        if not self._states:
            for t in self._transitions:
                if t.from_state not in self._states:
                    self._states[t.from_state] = State(name=t.from_state)
                if t.to_state not in self._states:
                    self._states[t.to_state] = State(name=t.to_state)

        # Populate allowed_transitions from transition list
        for t in self._transitions:
            state = self._states.get(t.from_state)
            if state and t.to_state not in state.allowed_transitions:
                state.allowed_transitions.append(t.to_state)

        if self._initial_state not in self._states:
            raise ValueError(
                f"StateMachine: initial_state '{initial_state}' not found in states"
            )

        logger.debug("StateMachine: initialized in state '%s'", self._initial_state)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> str:
        """Return the name of the current state."""
        with self._lock:
            return self._current_state

    def can_transition(self, to_state: str) -> bool:
        """
        Check whether a transition to *to_state* is allowed from the
        current state **and** all guard conditions pass.

        Returns:
            True if the transition is allowed, False otherwise.
        """
        with self._lock:
            return self._can_transition_internal(to_state)

    def transition(self, to_state: str) -> bool:
        """
        Attempt a transition to *to_state*.

        The transition succeeds only if:
          1. *to_state* is in the current state's ``allowed_transitions``.
          2. A matching :class:`Transition` exists.
          3. The transition's ``condition`` (if any) returns True.
          4. The current state's ``on_exit`` callback runs without error.
          5. The target state's ``on_enter`` callback runs without error.

        Returns:
            True if the transition was performed, False otherwise.
        """
        with self._lock:
            from_state = self._current_state

            if not self._can_transition_internal(to_state):
                logger.warning(
                    "StateMachine: transition '%s' → '%s' not allowed",
                    from_state, to_state,
                )
                return False

            # Find matching transition
            matched_trans = self._find_transition(from_state, to_state)
            if matched_trans is None:
                return False

            # Execute action (if any)
            if matched_trans.action:
                try:
                    matched_trans.action()
                except Exception as exc:
                    logger.error(
                        "StateMachine: transition action failed – %s", exc
                    )
                    return False

            # on_exit
            old_state_obj = self._states.get(from_state)
            if old_state_obj and old_state_obj.on_exit:
                try:
                    old_state_obj.on_exit(to_state)
                except Exception as exc:
                    logger.error("StateMachine: on_exit failed – %s", exc)

            # Switch
            self._current_state = to_state

            # on_enter
            new_state_obj = self._states.get(to_state)
            if new_state_obj and new_state_obj.on_enter:
                try:
                    new_state_obj.on_enter(from_state)
                except Exception as exc:
                    logger.error("StateMachine: on_enter failed – %s", exc)

            # Record history
            self._history.append({
                "from": from_state,
                "to": to_state,
                "timestamp": self._now(),
            })

            logger.info("StateMachine: transitioned '%s' → '%s'", from_state, to_state)
            return True

    def reset(self) -> None:
        """Reset the machine to its initial state and clear history."""
        with self._lock:
            self._current_state = self._initial_state
            self._history.clear()
            logger.debug("StateMachine: reset to initial state '%s'", self._initial_state)

    @property
    def history(self) -> List[Dict[str, Any]]:
        """Return a copy of the transition history."""
        with self._lock:
            return list(self._history)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _can_transition_internal(self, to_state: str) -> bool:
        """Unlocked check — caller must hold ``self._lock``."""
        from_state = self._current_state
        state_obj = self._states.get(from_state)
        if state_obj is None:
            return False
        if to_state not in state_obj.allowed_transitions:
            return False
        # Check condition
        trans = self._find_transition(from_state, to_state)
        if trans is None:
            return False
        if trans.condition and not trans.condition():
            return False
        return True

    def _find_transition(self, from_state: str, to_state: str) -> Optional[Transition]:
        """Find the first matching transition definition."""
        for t in self._transitions:
            if t.from_state == from_state and t.to_state == to_state:
                return t
        return None

    @staticmethod
    def _now() -> float:
        import time
        return time.monotonic()
