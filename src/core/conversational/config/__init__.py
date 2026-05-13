"""
Configuracion del Asistente.

Carga desde .env + defaults + YAML, con validacion
y valores por defecto seguros para produccion.
"""

from .env import AgentsConfig, load_agents_config, get_config
from .constants import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_PORT,
    DEFAULT_HOST,
    SESSION_TIMEOUT_SECONDS,
    MAX_SESSIONS,
    MAX_MESSAGES_PER_SESSION,
    MAX_CONTEXT_TOKENS,
    STREAMING_CHUNK_SIZE,
    RATE_LIMIT_RPM,
    HEALTH_CHECK_INTERVAL_SECONDS,
    PERSONALITY_DEFAULT,
)

__all__ = [
    "AgentsConfig",
    "load_agents_config",
    "get_config",
    "APP_NAME",
    "APP_VERSION",
    "DEFAULT_PORT",
    "DEFAULT_HOST",
    "SESSION_TIMEOUT_SECONDS",
    "MAX_SESSIONS",
    "MAX_MESSAGES_PER_SESSION",
    "MAX_CONTEXT_TOKENS",
    "STREAMING_CHUNK_SIZE",
    "RATE_LIMIT_RPM",
    "HEALTH_CHECK_INTERVAL_SECONDS",
    "PERSONALITY_DEFAULT",
]
