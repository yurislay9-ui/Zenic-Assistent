"""
Servidor del Asistente.

FastAPI con endpoints REST, WebSocket para streaming,
middleware de autenticacion y health checks.
"""

from .app import create_app, AgentsApp

__all__ = ["create_app", "AgentsApp"]
