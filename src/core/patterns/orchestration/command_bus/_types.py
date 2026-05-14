"""CommandBus - Types and data contracts."""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional


# ============================================================
#  DATA CONTRACTS
# ============================================================

@dataclass
class Command:
    """
    Command payload dispatched through the CommandBus.

    Attributes:
        command_type: Identifier used to route to the correct handler.
        payload: Arbitrary data carried by the command.
        timestamp: Unix timestamp of command creation (auto-set).
        command_id: Unique identifier for this command (auto-generated).
    """
    command_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.command_type:
            raise ValueError("command_type must not be empty")


@dataclass
class CommandResult:
    """
    Result returned by a CommandHandler after processing a Command.

    Attributes:
        success: Whether the command was handled successfully.
        data: Result data from the handler.
        error: Error message if success is False.
        command_id: The ID of the command that produced this result.
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    command_id: str = ""


# ============================================================
#  HANDLER INTERFACE
# ============================================================

class CommandHandler(ABC):
    """
    Abstract base class for command handlers.

    Subclasses implement `handle` to process a Command and return a CommandResult.
    Each handler is registered for a specific command_type.
    """

    @abstractmethod
    def handle(self, command: Command) -> CommandResult:
        """
        Process the given command and return a result.

        Args:
            command: The Command to process.

        Returns:
            A CommandResult indicating success or failure.
        """
        ...


# ============================================================
#  MIDDLEWARE AND VALIDATOR TYPES
# ============================================================

# Middleware: pre/post processing around command execution.
# Signature: (command, next_handler) -> CommandResult
# - command: The incoming Command
# - next_handler: Callable that invokes the next middleware or handler
CommandMiddleware = Callable[
    [Command, Callable[[Command], CommandResult]],
    CommandResult,
]

# Async variant
AsyncCommandMiddleware = Callable[
    [Command, Callable[[Command], Awaitable[CommandResult]]],
    Awaitable[CommandResult],
]

# Validator: validates a command before dispatch.
# Returns True if valid, False (or raises) if invalid.
CommandValidator = Callable[[Command], bool]
