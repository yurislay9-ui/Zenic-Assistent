"""
ZENIC-AGENTS - Command Bus (Command Pattern)

Formal Command pattern implementation for replacing the StepDispatcher's
if/elif chain with a type-driven dispatch mechanism.

Features:
- Type-based command routing (replaces if/elif chains)
- Middleware pipeline for pre/post processing
- Validator pipeline for command validation before dispatch
- Sync, async, and batch dispatch modes
- Thread-safe handler registration and dispatch
- Statistics tracking for observability

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

import logging
import threading
from typing import Dict, List

from ._types import (
    Command,
    CommandHandler,
    CommandResult,
    CommandMiddleware,
    CommandValidator,
)

logger = logging.getLogger("zenic_agents.patterns.orchestration.command_bus")

__all__ = [
    "Command",
    "CommandHandler",
    "CommandResult",
    "CommandBus",
]


# ============================================================
#  COMMAND BUS
# ============================================================


from ._core_mixin import CommandBusCoreMixin
from ._extra_mixin import CommandBusExtraMixin


class CommandBus(CommandBusCoreMixin, CommandBusExtraMixin):
    """
    Formal Command Bus with middleware and validation support.

    Routes commands to registered handlers based on command_type.
    Supports middleware for cross-cutting concerns and validators
    for pre-dispatch command validation.

    Usage::

        bus = CommandBus()

        class AnalyzeHandler(CommandHandler):
            def handle(self, command):
                return CommandResult(
                    success=True,
                    data={"analysis": "done"},
                    command_id=command.command_id,
                )

        bus.register("ANALYZE_STRUCTURE", AnalyzeHandler())

        result = bus.dispatch(Command(
            command_type="ANALYZE_STRUCTURE",
            payload={"target": "main.py"},
        ))

    Middleware::

        def logging_middleware(command, next_handler):
            logger.info("Dispatching: %s", command.command_type)
            result = next_handler(command)
            logger.info("Result: %s", result.success)
            return result

        bus.add_middleware(logging_middleware)

    Validators::

        def require_target(command):
            return "target" in command.payload

        bus.add_validator(require_target)

    Thread Safety:
        All operations are protected by threading.Lock.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, CommandHandler] = {}
        self._middlewares: List[CommandMiddleware] = []
        self._validators: List[CommandValidator] = []
        self._lock = threading.Lock()
        self._dispatch_count: int = 0
        self._error_count: int = 0
        self._validation_reject_count: int = 0

    # ----------------------------------------------------------
    #  HANDLER REGISTRATION
    # ----------------------------------------------------------
