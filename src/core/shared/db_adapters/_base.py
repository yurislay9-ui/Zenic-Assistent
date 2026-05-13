"""
ZENIC-AGENTS v16 - Database Backend Abstract Base Class
"""

from typing import Any, Dict, List, Optional


class DatabaseBackend:
    """Abstract base class for database operations.

    Provides a unified async API that both SQLite and PostgreSQL
    adapters implement. All methods use parameterized queries to
    prevent SQL injection.
    """

    backend_name: str = "abstract"

    async def initialize(self) -> None:
        """Initialize database tables and connections."""
        raise NotImplementedError

    async def close(self) -> None:
        """Close all connections gracefully."""
        raise NotImplementedError

    async def connection(self) -> Any:
        """Get a database connection/context manager."""
        raise NotImplementedError

    async def execute(self, conn: Any, query: str, params: Optional[tuple] = None) -> None:
        """Execute a write query (INSERT, UPDATE, DELETE, DDL)."""
        raise NotImplementedError

    async def fetch_one(self, conn: Any, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """Fetch a single row as a dict."""
        raise NotImplementedError

    async def fetch_all(self, conn: Any, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Fetch all rows as a list of dicts."""
        raise NotImplementedError

    async def fetch_val(self, conn: Any, query: str, params: Optional[tuple] = None) -> Any:
        """Fetch a single scalar value."""
        raise NotImplementedError

    def format_param(self, index: int) -> str:
        """Return the parameter placeholder for position index (0-based).

        SQLite uses '?' while PostgreSQL uses '$1', '$2', etc.
        """
        raise NotImplementedError

    def adapt_query(self, query: str) -> str:
        """Adapt a SQLite-style query (?) to the backend's placeholder style.

        Replaces '?' placeholders with the appropriate format for the backend.
        """
        if self.backend_name == "sqlite":
            return query
        # Replace ? with $1, $2, etc. for PostgreSQL
        result = []
        param_idx = 1
        for char in query:
            if char == '?':
                result.append(f"${param_idx}")
                param_idx += 1
            else:
                result.append(char)
        return "".join(result)
