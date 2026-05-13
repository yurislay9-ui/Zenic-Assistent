"""CommandBus - Core methods."""

import logging
from typing import Callable, List, Optional

from ._types import Command, CommandHandler, CommandMiddleware, CommandResult, CommandValidator
from ._helpers import _build_middleware_chain

logger = logging.getLogger("zenic_agents.patterns.orchestration.command_bus")


class CommandBusCoreMixin:
    """Core methods mixin."""

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

    def register(self, command_type: str, handler: CommandHandler) -> None:
        """
        Register a handler for a specific command type.

        Args:
            command_type: The command type this handler processes.
            handler: A CommandHandler instance.

        Raises:
            ValueError: If command_type is empty or handler is None.
        """
        if not command_type:
            raise ValueError("command_type must not be empty")
        if handler is None:
            raise ValueError("handler must not be None")

        with self._lock:
            self._handlers[command_type] = handler
            logger.info(
                "CommandBus: Registered handler %s for command_type '%s'",
                type(handler).__name__, command_type,
            )

    # ----------------------------------------------------------
    #  MIDDLEWARE
    # ----------------------------------------------------------

    def add_middleware(self, middleware_fn: CommandMiddleware) -> None:
        """
        Add middleware that wraps command handler execution.

        Middleware is executed in the order it is added. Each middleware
        receives the command and a `next` callable that invokes the
        next middleware (or the actual handler if last).

        Use middleware for:
        - Logging
        - Metrics/timing
        - Transaction management
        - Error handling wrappers

        Args:
            middleware_fn: A callable with signature
                          (command, next_handler) -> CommandResult
        """
        if middleware_fn is None:
            raise ValueError("middleware_fn must not be None")

        with self._lock:
            self._middlewares.append(middleware_fn)
            logger.debug(
                "CommandBus: Added middleware '%s'",
                getattr(middleware_fn, '__name__', repr(middleware_fn)),
            )

    # ----------------------------------------------------------
    #  VALIDATORS
    # ----------------------------------------------------------

    def add_validator(self, validator_fn: CommandValidator) -> None:
        """
        Add a validator that checks commands before dispatch.

        Validators are executed in order. If ANY validator returns
        False, the command is rejected with a validation error.

        Use validators for:
        - Input validation
        - Authorization checks
        - Schema validation

        Args:
            validator_fn: A callable with signature (command) -> bool
        """
        if validator_fn is None:
            raise ValueError("validator_fn must not be None")

        with self._lock:
            self._validators.append(validator_fn)
            logger.debug(
                "CommandBus: Added validator '%s'",
                getattr(validator_fn, '__name__', repr(validator_fn)),
            )

    # ----------------------------------------------------------
    #  VALIDATION
    # ----------------------------------------------------------

    def _validate(self, command: Command) -> Optional[str]:
        """
        Run all validators against a command.

        Args:
            command: The Command to validate.

        Returns:
            None if all validators pass, or an error message string.
        """
        with self._lock:
            validators = list(self._validators)

        for validator in validators:
            try:
                if not validator(command):
                    validator_name = getattr(
                        validator, '__name__', repr(validator)
                    )
                    return f"Validation failed: {validator_name}"
            except Exception as exc:
                validator_name = getattr(
                    validator, '__name__', repr(validator)
                )
                return f"Validation error in {validator_name}: {exc}"

        return None

    # ----------------------------------------------------------
    #  SYNC DISPATCH
    # ----------------------------------------------------------

    def dispatch(self, command: Command) -> CommandResult:
        """
        Synchronously dispatch a command to its registered handler.

        Runs validators first. If validation fails, returns an error
        CommandResult. Then applies middleware chain around the handler.

        Args:
            command: The Command to dispatch.

        Returns:
            A CommandResult from the handler (or error/validation result).
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(command.command_type)
            middlewares = list(self._middlewares)

        # Log dispatch
        logger.info(
            "CommandBus: Dispatching command_type='%s' id='%s' "
            "(middlewares=%d, validators=%d)",
            command.command_type, command.command_id[:8],
            len(middlewares), len(self._validators),
        )

        # Validate
        validation_error = self._validate(command)
        if validation_error is not None:
            self._validation_reject_inc()
            logger.warning(
                "CommandBus: Command '%s' rejected: %s",
                command.command_id[:8], validation_error,
            )
            return CommandResult(
                success=False,
                error=validation_error,
                command_id=command.command_id,
            )

        # Check handler exists
        if handler is None:
            error_msg = (
                f"No handler registered for command_type "
                f"'{command.command_type}'"
            )
            logger.warning("CommandBus: %s", error_msg)
            self._error_count_inc()
            return CommandResult(
                success=False,
                error=error_msg,
                command_id=command.command_id,
            )

        # Build middleware chain
        try:
            chain = _build_middleware_chain(handler.handle, middlewares)
            result = chain(command)
            return result
        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "CommandBus: Handler failed for command_type '%s': %s",
                command.command_type, exc,
                exc_info=True,
            )
            return CommandResult(
                success=False,
                error=str(exc),
                command_id=command.command_id,
            )

    # ----------------------------------------------------------
    #  ASYNC DISPATCH
    # ----------------------------------------------------------

