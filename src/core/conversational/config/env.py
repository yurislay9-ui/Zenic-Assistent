"""
Carga de configuracion desde entorno.

Lee variables de entorno con prefijo ZENIC_AGENTS_,
las valida y proporciona defaults seguros.

Variables soportadas:
  ZENIC_AGENTS_HOST          - Host de bind (default: 0.0.0.0)
  ZENIC_AGENTS_PORT          - Puerto (default: 5000)
  ZENIC_AGENTS_LOG_LEVEL     - Nivel de log (default: INFO)
  ZENIC_AGENTS_MAX_SESSIONS  - Max sesiones (default: 100)
  ZENIC_AGENTS_RATE_LIMIT    - RPM limite (default: 60)
  ZENIC_AGENTS_PERSONALITY   - Personalidad (default: zenic)
  ZENIC_AGENTS_LANGUAGE      - Idioma (default: es)
  ZENIC_AGENTS_STREAMING     - Streaming activo (default: true)
  ZENIC_AGENTS_TOOLS         - Tools activas (default: true)
  ZENIC_AGENTS_MEMORY        - Memoria activa (default: true)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from .constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    LOG_LEVEL_DEFAULT,
    MAX_SESSIONS,
    RATE_LIMIT_RPM,
    PERSONALITY_DEFAULT,
)

# Prefijo para variables de entorno
ENV_PREFIX = "ZENIC_AGENTS_"


@dataclass
class AgentsConfig:
    """
    Configuracion completa del agente.

    Cargada desde variables de entorno con defaults seguros.
    Inmutable por diseno — no se modifica en runtime.
    """
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = LOG_LEVEL_DEFAULT
    max_sessions: int = MAX_SESSIONS
    rate_limit_rpm: int = RATE_LIMIT_RPM
    personality: str = PERSONALITY_DEFAULT
    language: str = "es"
    streaming_enabled: bool = True
    tools_enabled: bool = True
    memory_enabled: bool = True
    debug: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    database_url: str = ""
    api_key: str = ""                # API key opcional para proteccion

    def to_dict(self) -> dict[str, object]:
        """Convierte la config a diccionario (sin datos sensibles)."""
        d = {
            "host": self.host,
            "port": self.port,
            "log_level": self.log_level,
            "max_sessions": self.max_sessions,
            "rate_limit_rpm": self.rate_limit_rpm,
            "personality": self.personality,
            "language": self.language,
            "streaming_enabled": self.streaming_enabled,
            "tools_enabled": self.tools_enabled,
            "memory_enabled": self.memory_enabled,
            "debug": self.debug,
        }
        if self.api_key:
            d["api_key"] = "***"  # No exponer
        return d


def _get_env(name: str, default: str = "") -> str:
    """Lee una variable de entorno con el prefijo."""
    return os.environ.get(f"{ENV_PREFIX}{name}", default)


def _get_env_int(name: str, default: int = 0) -> int:
    """Lee una variable de entorno entera."""
    val = _get_env(name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _get_env_bool(name: str, default: bool = True) -> bool:
    """Lee una variable de entorno booleana."""
    val = _get_env(name).lower()
    if not val:
        return default
    return val in ("true", "1", "yes", "on", "si")


def load_agents_config() -> AgentsConfig:
    """
    Carga la configuracion desde variables de entorno.

    Returns:
        AgentsConfig con valores de entorno o defaults.
    """
    cors_raw = _get_env("CORS_ORIGINS", "*")
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]

    return AgentsConfig(
        host=_get_env("HOST", DEFAULT_HOST),
        port=_get_env_int("PORT", DEFAULT_PORT),
        log_level=_get_env("LOG_LEVEL", LOG_LEVEL_DEFAULT).upper(),
        max_sessions=_get_env_int("MAX_SESSIONS", MAX_SESSIONS),
        rate_limit_rpm=_get_env_int("RATE_LIMIT", RATE_LIMIT_RPM),
        personality=_get_env("PERSONALITY", PERSONALITY_DEFAULT),
        language=_get_env("LANGUAGE", "es"),
        streaming_enabled=_get_env_bool("STREAMING", True),
        tools_enabled=_get_env_bool("TOOLS", True),
        memory_enabled=_get_env_bool("MEMORY", True),
        debug=_get_env_bool("DEBUG", False),
        cors_origins=cors_origins,
        database_url=_get_env("DATABASE_URL", ""),
        api_key=_get_env("API_KEY", ""),
    )


# ─── Singleton ────────────────────────────────────────────────

_config: Optional[AgentsConfig] = None


def get_config() -> AgentsConfig:
    """
    Obtiene la configuracion global (singleton).

    La carga en la primera llamada y la cachea.
    Para forzar recarga, llamar load_agents_config() directamente.
    """
    global _config
    if _config is None:
        _config = load_agents_config()
    return _config


def reset_config() -> None:
    """Resetea el singleton de configuracion (para tests)."""
    global _config
    _config = None
