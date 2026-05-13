"""CommandBus - Helper functions for middleware chain."""

from typing import Callable, List

from ._types import Command, CommandMiddleware, CommandResult


def _build_middleware_chain(
    handler_fn: Callable[[Command], CommandResult],
    middlewares: List[CommandMiddleware],
) -> Callable[[Command], CommandResult]:
    """
    Build a chain of middleware wrapping a handler.

    Middleware is applied in reverse order so that the first middleware
    added is the outermost wrapper (executed first).

    Args:
        handler_fn: The actual handler callable.
        middlewares: List of middleware functions.

    Returns:
        A callable that applies all middleware then the handler.
    """
    chain = handler_fn
    for middleware in reversed(middlewares):
        chain = _wrap_middleware(chain, middleware)
    return chain


def _wrap_middleware(
    next_fn: Callable[[Command], CommandResult],
    middleware: CommandMiddleware,
) -> Callable[[Command], CommandResult]:
    """
    Wrap a handler callable with a middleware.

    Args:
        next_fn: The next handler or middleware in the chain.
        middleware: The middleware to wrap around next_fn.

    Returns:
        A new callable that applies the middleware.
    """
    def _wrapped(command: Command) -> CommandResult:
        return middleware(command, next_fn)
    return _wrapped
