"""CommandBus - Additional methods."""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

from ._types import Command, CommandMiddleware, CommandResult

logger = logging.getLogger("zenic_agents.patterns.orchestration.command_bus")


class CommandBusExtraMixin:
    """Additional methods mixin."""

    async def dispatch_async(self, command: Command) -> CommandResult:
        """
        Asynchronously dispatch a command to its registered handler.

        Supports async handlers and middleware. Sync handlers are
        automatically wrapped to run in the default executor.

        Args:
            command: The Command to dispatch.

        Returns:
            A CommandResult from the handler (or error/validation result).
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(command.command_type)
            middlewares = list(self._middlewares)

        logger.info(
            "CommandBus[async]: Dispatching command_type='%s' id='%s'",
            command.command_type, command.command_id[:8],
        )

        # Validate
        validation_error = self._validate(command)
        if validation_error is not None:
            self._validation_reject_inc()
            return CommandResult(
                success=False,
                error=validation_error,
                command_id=command.command_id,
            )

        # Check handler
        if handler is None:
            error_msg = (
                f"No handler registered for command_type "
                f"'{command.command_type}'"
            )
            self._error_count_inc()
            return CommandResult(
                success=False,
                error=error_msg,
                command_id=command.command_id,
            )

        try:
            # Wrap handler as async
            async def _async_handle(cmd: Command) -> CommandResult:
                result = handler.handle(cmd)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            # Build async middleware chain
            chain: Callable[[Command], Awaitable[CommandResult]] = _async_handle

            for mw in reversed(middlewares):
                prev_chain = chain

                async def _make_async_mw(
                    cmd: Command,
                    _mw: CommandMiddleware = mw,
                    _next: Callable[
                        [Command], Awaitable[CommandResult]
                    ] = prev_chain,
                ) -> CommandResult:
                    # Run sync middleware; adapt async next
                    def _sync_next(c: Command) -> CommandResult:
                        # Run the async chain in a new event loop
                        # inside a dedicated thread to avoid
                        # "cannot run the event loop while another
                        # loop is running" errors on Xiaomi.
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as pool:
                            future = pool.submit(asyncio.run, _next(c))
                            return future.result()

                    return _mw(cmd, _sync_next)

                chain = _make_async_mw  # type: ignore[assignment]

            result = await chain(command)
            return result

        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "CommandBus[async]: Handler failed for command_type '%s': %s",
                command.command_type, exc,
                exc_info=True,
            )
            return CommandResult(
                success=False,
                error=str(exc),
                command_id=command.command_id,
            )

    # ----------------------------------------------------------
    #  BATCH DISPATCH
    # ----------------------------------------------------------

    def dispatch_all(self, commands: List[Command]) -> List[CommandResult]:
        """
        Synchronously dispatch multiple commands in sequence.

        Each command is dispatched independently. A failure in one
        command does not affect subsequent commands.

        Args:
            commands: List of Commands to dispatch.

        Returns:
            List of CommandResults, one per command, in order.
        """
        if not commands:
            return []

        results: List[CommandResult] = []
        logger.info(
            "CommandBus: Batch dispatching %d commands", len(commands),
        )

        for command in commands:
            result = self.dispatch(command)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        logger.info(
            "CommandBus: Batch complete: %d/%d successful",
            successful, len(commands),
        )

        return results

    # ----------------------------------------------------------
    #  UTILITIES
    # ----------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """
        Runtime statistics for monitoring and debugging.

        Returns:
            Dict with:
            - dispatch_count: Total commands dispatched
            - errors_count: Total dispatch errors
            - validation_reject_count: Total commands rejected by validators
            - registered_handlers: Number of registered handlers
            - registered_types: List of registered command types
            - middleware_count: Number of registered middleware
            - validator_count: Number of registered validators
        """
        with self._lock:
            return {
                "dispatch_count": self._dispatch_count,
                "errors_count": self._error_count,
                "validation_reject_count": self._validation_reject_count,
                "registered_handlers": len(self._handlers),
                "registered_types": list(self._handlers.keys()),
                "middleware_count": len(self._middlewares),
                "validator_count": len(self._validators),
            }

    def _error_count_inc(self) -> None:
        """Increment error counter in a thread-safe manner."""
        with self._lock:
            self._error_count += 1

    def _validation_reject_inc(self) -> None:
        """Increment validation reject counter in a thread-safe manner."""
        with self._lock:
            self._validation_reject_count += 1

