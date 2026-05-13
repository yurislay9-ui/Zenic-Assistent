"""
ZENIC-AGENTS - Environment Loader v16

Cargador de archivos .env puro Python (SIN dependencias externas).
Compatible con Android/Termux, zero overhead.

Funcionalidades:
- Parsea archivos .env (KEY=VALUE, comentarios #, comillas opcionales)
- Solo sobreescribe variables que NO existan ya en os.environ
  (las variables del sistema tienen prioridad sobre .env)
- Soporta valores con espacios y comillas (simple/doble)
- Ignora lineas vacias y comentarios
- Busca .env en: CWD, proyecto raiz, ~/.zenic_agents/
- Thread-safe (carga una sola vez)

Uso:
    from src.core.env_loader import load_env, get_env
    load_env()  # Carga .env al inicio
    token = get_env("GITHUB_TOKEN", default="")
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

import threading
_load_lock = threading.Lock()

# Estado interno (carga unica)
_loaded = False
_loaded_path: Optional[str] = None


def _parse_env_line(line: str) -> Optional[tuple]:
    """
    Parsea una linea de .env y devuelve (key, value) o None.

    Formatos soportados:
        KEY=VALUE
        KEY="VALUE WITH SPACES"
        KEY='VALUE WITH SPACES'
        # Comentario (ignorado)
        LINEA_VACIA (ignorada)
    """
    line = line.strip()

    # Ignorar lineas vacias y comentarios
    if not line or line.startswith('#'):
        return None

    # Debe tener al menos un = para ser valida
    if '=' not in line:
        return None

    # Separar en la PRIMERA ocurrencia de =
    key, _, value = line.partition('=')
    key = key.strip()
    value = value.strip()

    if not key:
        return None

    # Remover comillas si el valor esta envuelto en ellas
    if len(value) >= 2:
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

    return key, value


def _find_env_file() -> Optional[Path]:
    """
    Busca el archivo .env en orden de prioridad:
    1. Directorio de trabajo actual (CWD)
    2. Directorio del proyecto (donde esta pyproject.toml)
    3. ~/.zenic_agents/.env (configuracion global)
    """
    candidates = []

    # 1. CWD
    cwd = Path.cwd()
    candidates.append(cwd / ".env")

    # 2. Buscar raiz del proyecto (donde esta pyproject.toml)
    try:
        # Subir hasta encontrar pyproject.toml o llegar a /
        current = Path(__file__).resolve().parent
        for _ in range(10):  # Max 10 niveles hacia arriba
            if (current / "pyproject.toml").exists():
                candidates.append(current / ".env")
                break
            parent = current.parent
            if parent == current:
                break
            current = parent
    except Exception:
        pass

    # 3. ~/.zenic_agents/.env (global config)
    home = Path.home()
    candidates.append(home / ".zenic_agents" / ".env")

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    return None


def load_env(force: bool = False) -> bool:
    """
    Carga variables de entorno desde archivo .env.

    Solo sobreescribe variables que NO existan ya en os.environ.
    Las variables del sistema (export GITHUB_TOKEN=xxx) tienen
    prioridad sobre las del archivo .env.

    Args:
        force: Si True, recarga incluso si ya se cargo antes.

    Returns:
        True si se cargo exitosamente, False si no se encontro .env
    """
    global _loaded, _loaded_path

    with _load_lock:
        if _loaded and not force:
            return _loaded_path is not None

        env_path = _find_env_file()

        if env_path is None:
            logger.debug("env_loader: No .env file found")
            _loaded = True
            return False

        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (OSError, PermissionError) as e:
            logger.warning("env_loader: Cannot read %s: %s", env_path, e)
            _loaded = True
            return False

        loaded_count = 0
        skipped_count = 0

        for line_num, line in enumerate(lines, 1):
            parsed = _parse_env_line(line)
            if parsed is None:
                continue

            key, value = parsed

            # Solo setear si NO existe ya en os.environ
            # (el entorno del sistema tiene prioridad)
            if key not in os.environ:
                os.environ[key] = value
                loaded_count += 1
            else:
                skipped_count += 1

        _loaded = True
        _loaded_path = str(env_path)

        logger.info(
            "env_loader: Loaded %d vars from %s (%d skipped, already in env)",
            loaded_count, env_path.name, skipped_count
        )
        return True


def get_env(key: str, default: str = "") -> str:
    """
    Obtiene una variable de entorno, cargando .env si no se ha hecho.

    Args:
        key: Nombre de la variable
        default: Valor por defecto si no existe

    Returns:
        Valor de la variable o default
    """
    if not _loaded:
        load_env()
    return os.environ.get(key, default)


def get_env_int(key: str, default: int = 0) -> int:
    """Obtiene una variable de entorno como entero."""
    value = get_env(key, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """
    Obtiene una variable de entorno como booleano.

    Valores truthy: true, yes, 1, on (case-insensitive)
    Valores falsy: false, no, 0, off, vacio (case-insensitive)
    """
    value = get_env(key, "").lower()
    if value in ("true", "yes", "1", "on"):
        return True
    if value in ("false", "no", "0", "off", ""):
        return default if value == "" else False
    return default


def get_env_list(key: str, default: Optional[list] = None, separator: str = ",") -> list:
    """Obtiene una variable de entorno como lista (separada por comas)."""
    value = get_env(key, "")
    if not value:
        return default or []
    return [item.strip() for item in value.split(separator) if item.strip()]


def get_loaded_path() -> Optional[str]:
    """Retorna la ruta del .env cargado, o None si no se cargo."""
    return _loaded_path


def get_github_token() -> str:
    """
    Obtiene el token de GitHub desde el entorno.
    Busca GITHUB_TOKEN primero, luego GITHUB_API_KEY como fallback.
    """
    token = get_env("GITHUB_TOKEN", "")
    if not token:
        token = get_env("GITHUB_API_KEY", "")
    return token


def get_metrics_config() -> dict:
    """
    Obtiene la configuracion de metricas de GitHub desde .env.

    Returns:
        dict con: enabled, collect, refresh_interval
    """
    return {
        "enabled": get_env_bool("GITHUB_METRICS_ENABLED", True),
        "collect": get_env_list("GITHUB_METRICS_COLLECT",
                                ["rate_limit", "search_results", "repo_stats"]),
        "refresh_interval": get_env_int("GITHUB_METRICS_REFRESH_INTERVAL", 300),
    }


def get_scraper_config() -> dict:
    """
    Obtiene la configuracion del Scraper Inteligente desde .env.

    Returns:
        dict con: timeout, max_retries, max_chars, preferred_source,
                  devdocs_url, iconstack_url, picsum_url,
                  picsum_width, picsum_height, devdocs_languages,
                  iconstack_style
    """
    return {
        "timeout": get_env_int("SCRAPER_TIMEOUT", 10),
        "max_retries": get_env_int("SCRAPER_MAX_RETRIES", 2),
        "max_chars": get_env_int("SCRAPER_MAX_CHARS", 2000),
        "preferred_source": get_env("SCRAPER_PREFERRED_SOURCE", "auto"),
        "github_token": get_github_token(),
        # DevDocs
        "devdocs_url": get_env("DEVDOCS_BASE_URL", "https://devdocs.io"),
        "devdocs_languages": get_env_list("DEVDOCS_DEFAULT_LANGUAGES",
                                          ["python", "kotlin", "javascript",
                                           "typescript", "html", "css"]),
        # IconStack
        "iconstack_url": get_env("ICONSTACK_BASE_URL", "https://icon-icons.com"),
        "iconstack_style": get_env("ICONSTACK_DEFAULT_STYLE", "material"),
        # Picsum
        "picsum_url": get_env("PICSUM_BASE_URL", "https://picsum.photos"),
        "picsum_width": get_env_int("PICSUM_DEFAULT_WIDTH", 800),
        "picsum_height": get_env_int("PICSUM_DEFAULT_HEIGHT", 600),
        # GitHub Metrics
        "metrics": get_metrics_config(),
    }
