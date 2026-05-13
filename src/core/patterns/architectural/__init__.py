"""
ZENIC-AGENTS - Architectural Patterns Facade

Re-exports the public API of the architectural pattern sub-package.
"""

from src.core.patterns.architectural.cqrs import (
    CQRSBus,
    Command,
    Query,
    CommandHandler,
    QueryHandler,
)

__all__ = [
    "CQRSBus",
    "Command",
    "Query",
    "CommandHandler",
    "QueryHandler",
]
