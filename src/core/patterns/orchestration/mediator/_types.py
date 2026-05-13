"""
ZENIC-AGENTS - Mediator Pattern: Data Contracts and Handler Interface
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union


@dataclass
class Request:
    """
    Request payload dispatched through the Mediator.

    Attributes:
        request_type: Identifier used to route to the correct handler.
        payload: Arbitrary data carried by the request.
        metadata: Optional metadata for logging/tracing.
    """
    request_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_type:
            raise ValueError("request_type must not be empty")


@dataclass
class Response:
    """
    Response returned by a RequestHandler.

    Attributes:
        success: Whether the request was handled successfully.
        data: Result data from the handler.
        error: Error message if success is False.
        source: Identifier of the handler that produced this response.
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    source: str = ""


class RequestHandler(ABC):
    """
    Abstract base class for request handlers.

    Subclasses implement `handle` to process a Request and return a Response.
    Each handler is registered for a specific request_type.
    """

    @abstractmethod
    def handle(self, request: Request) -> Response:
        """
        Process the given request and return a response.

        Args:
            request: The Request to process.

        Returns:
            A Response indicating success or failure.
        """
        ...


# Pipeline behavior type aliases
# A pipeline behavior is a callable that wraps handler execution.
# Signature: (request, next_handler) -> Response
PipelineBehavior = Callable[[Request, Callable[[Request], Response]], Response]

# Async variant
AsyncPipelineBehavior = Callable[
    [Request, Callable[[Request], Awaitable[Response]]],
    Awaitable[Response],
]
