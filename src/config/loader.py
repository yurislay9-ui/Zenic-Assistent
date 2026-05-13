"""
ZENIC-AGENTS - Configuration Loader v16

Cargador de configuracion desde YAML y variables de entorno.
Lee settings.yaml y combina con overrides de entorno.

Funciones exportadas:
- load_settings(): Carga configuracion completa
- get_solver_timeout_ms(): Timeout quirurgico del solver (ms)
- get_solver_fast_timeout_ms(): Timeout rapido del solver (ms)
- get_mcts_config(): Configuracion de MCTS
- get_k_path_limit(): Limite de K-Paths
- get_sandbox_timeout_s(): Timeout del sandbox (segundos)
- get_critical_nodes(): Lista de nodos criticos
- get_critical_patterns(): Patrones criticos para seguridad
- get_setting(): Acceso generico por clave punto
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Default settings (fallback if YAML is not available)
_DEFAULTS: Dict[str, Any] = {
    "project_dir": ".",
    "engine_limits": {
        "solver_timeout_ms": 15000,
        "solver_fast_timeout_ms": 5000,
        "sandbox_timeout_s": 5,
        "mcts_max_depth": 5,
        "mcts_max_simulations": 100,
        "max_k_paths": 10,
    },
    "scraper": {
        "timeout": 10,
        "max_retries": 2,
        "max_chars": 2000,
        "preferred_source": "auto",
    },
    "critical_nodes": [
        "auth", "login", "signin", "signup", "password", "token",
        "crypto", "cipher", "encrypt", "decrypt", "hash", "salt",
        "payment", "stripe", "paypal", "transaction", "billing",
        "db", "database", "sql", "migration", "schema",
        "session", "cookie", "jwt", "oauth", "saml",
    ],
    "critical_patterns": [
        "*auth*", "*login*", "*signin*", "*signup*", "*password*",
        "*token*", "*crypto*", "*cipher*", "*encrypt*", "*decrypt*",
        "*hash*", "*salt*", "*payment*", "*stripe*", "*paypal*",
        "*transaction*", "*billing*", "*db*", "*database*", "*sql*",
        "*migration*", "*schema*", "*session*", "*cookie*",
        "*jwt*", "*oauth*", "*saml*",
    ],
}

_settings_cache: Optional[Dict[str, Any]] = None


def _load_yaml(filepath: Path) -> Dict[str, Any]:
    """Carga un archivo YAML de forma segura (sin dependencias externas)."""
    try:
        import yaml
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Fallback: parser YAML minimalista si no hay PyYAML
        return _parse_yaml_simple(filepath)
    except Exception as e:
        logger.warning("Config: Cannot load %s: %s", filepath, e)
        return {}


def _parse_yaml_simple(filepath: Path) -> Dict[str, Any]:
    """
    Parser YAML minimalista para settings.yaml.
    Solo soporta el formato plano usado por el proyecto.
    """
    result: Dict[str, Any] = {}
    current_section = result
    current_key = None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.rstrip()
                if not stripped or stripped.startswith("#"):
                    continue

                # Detectar secciones (indent = 0 con :)
                if not line[0].isspace() and ":" in stripped:
                    key, _, value = stripped.partition(":")
                    key = key.strip()
                    value = value.strip()

                    if not value:
                        # Nueva seccion
                        current_section = {}
                        result[key] = current_section
                        current_key = key
                    else:
                        # Valor simple
                        result[key] = _parse_value(value)

                elif line[0].isspace() and ":" in stripped:
                    # Clave dentro de seccion
                    key, _, value = stripped.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if isinstance(current_section, dict):
                        current_section[key] = _parse_value(value)

    except Exception as e:
        logger.debug("Config: Simple YAML parse failed: %s", e)

    return result


def _parse_value(value: str) -> Any:
    """Parsea un valor simple de YAML."""
    if not value:
        return ""
    # Remover comillas
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    # Booleanos
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    # Enteros
    try:
        return int(value)
    except ValueError:
        pass
    # Flotantes
    try:
        return float(value)
    except ValueError:
        pass
    # Listas (simple: ["a", "b"])
    if value.startswith("[") and value.endswith("]"):
        items = value[1:-1].split(",")
        return [i.strip().strip('"').strip("'") for i in items if i.strip()]
    return value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Fusiona dos diccionarios recursivamente (override gana)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(force: bool = False) -> Dict[str, Any]:
    """
    Carga la configuracion del sistema.

    Orden de prioridad (mayor a menor):
    1. Variables de entorno (ZENIC_*, SCRAPER_*, etc.)
    2. settings.yaml
    3. Valores por defecto (_DEFAULTS)

    Args:
        force: Si True, ignora cache y recarga.

    Returns:
        Dict con la configuracion fusionada.
    """
    global _settings_cache

    if _settings_cache and not force:
        return _settings_cache

    # 1. Empezar con defaults (deep copy para evitar mutacion)
    settings = _deep_merge({}, _DEFAULTS)

    # 2. Cargar YAML si existe
    yaml_path = Path(__file__).parent / "settings.yaml"
    if yaml_path.exists():
        yaml_settings = _load_yaml(yaml_path)
        if yaml_settings:
            settings = _deep_merge(settings, yaml_settings)

    # 3. Overrides desde variables de entorno
    if os.environ.get("ZENIC_DATA_DIR"):
        settings["data_dir"] = os.environ["ZENIC_DATA_DIR"]

    _settings_cache = settings
    return settings


def get_setting(key: str, default: Any = None) -> Any:
    """Obtiene un valor de configuracion por clave (notacion punto)."""
    settings = load_settings()
    keys = key.split(".")
    current = settings
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


# ============================================================
#  ENGINE LIMITS - Accessores tipados para limits del solver
# ============================================================

def get_solver_timeout_ms(settings: Optional[Dict[str, Any]] = None) -> int:
    """
    Obtiene el timeout quirurgico del solver en milisegundos.

    Este es el limite maximo para operaciones criticas del solver
    Z3 (verificacion formal, constraint solving, etc.).

    Args:
        settings: Configuracion ya cargada (opcional).

    Returns:
        Timeout en milisegundos (default: 15000 = 15s).
    """
    if settings is None:
        settings = load_settings()
    limits = settings.get("engine_limits", _DEFAULTS["engine_limits"])
    return int(limits.get("solver_timeout_ms", 15000))


def get_solver_fast_timeout_ms(settings: Optional[Dict[str, Any]] = None) -> int:
    """
    Obtiene el timeout rapido del solver en milisegundos.

    Usado para operaciones no quirurgicas donde la velocidad
    es mas importante que la completitud.

    Args:
        settings: Configuracion ya cargada (opcional).

    Returns:
        Timeout en milisegundos (default: 5000 = 5s).
    """
    if settings is None:
        settings = load_settings()
    limits = settings.get("engine_limits", _DEFAULTS["engine_limits"])
    return int(limits.get("solver_fast_timeout_ms", 5000))


def get_mcts_config(settings: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """
    Obtiene la configuracion de MCTS (Monte Carlo Tree Search).

    Retorna un diccionario con los parametros de MCTS usados
    por el APAPlanner para explorar el arbol de decisiones.

    Args:
        settings: Configuracion ya cargada (opcional).

    Returns:
        Dict con: max_depth, max_simulations, timeout_ms.
    """
    if settings is None:
        settings = load_settings()
    limits = settings.get("engine_limits", _DEFAULTS["engine_limits"])
    return {
        "max_depth": int(limits.get("mcts_max_depth", 5)),
        "max_simulations": int(limits.get("mcts_max_simulations", 100)),
        "timeout_ms": int(limits.get("solver_timeout_ms", 15000)),
    }


def get_k_path_limit(settings: Optional[Dict[str, Any]] = None) -> int:
    """
    Obtiene el limite de K-Paths para analisis de caminos.

    K-Paths es el radio de caminos que el motor puede explorar
    durante el analisis simbolico y la ejecucion simbolica.

    Args:
        settings: Configuracion ya cargada (opcional).

    Returns:
        Limite de K-Paths (default: 10).
    """
    if settings is None:
        settings = load_settings()
    limits = settings.get("engine_limits", _DEFAULTS["engine_limits"])
    return int(limits.get("max_k_paths", 10))


def get_sandbox_timeout_s(settings: Optional[Dict[str, Any]] = None) -> float:
    """
    Obtiene el timeout del sandbox en segundos.

    El sandbox aísla la ejecución de código generado para
    validación antes de hacer commit.

    Args:
        settings: Configuracion ya cargada (opcional).

    Returns:
        Timeout en segundos (default: 5).
    """
    if settings is None:
        settings = load_settings()
    limits = settings.get("engine_limits", _DEFAULTS["engine_limits"])
    return float(limits.get("sandbox_timeout_s", 5))


# ============================================================
#  CRITICAL NODES & PATTERNS - Seguridad
# ============================================================

def get_critical_nodes(settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Obtiene la lista de nodos criticos desde la configuracion.

    Los nodos criticos son keywords que indican operaciones sensibles
    (auth, payment, crypto, etc.) que requieren validacion extra.

    Args:
        settings: Configuracion ya cargada (opcional, se carga si no se pasa).

    Returns:
        Lista de strings con los keywords criticos.
    """
    if settings is None:
        settings = load_settings()
    return settings.get("critical_nodes", _DEFAULTS["critical_nodes"])


def get_critical_patterns(settings: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Obtiene los patrones criticos para validacion de seguridad.

    Retorna una lista plana de patrones glob-style (fnmatch)
    usados por el MacroRouter para clasificar operaciones criticas.
    El router usa fnmatch.fnmatch(target, pattern) para matching.

    Args:
        settings: Configuracion ya cargada (opcional).

    Returns:
        Lista de patrones glob-style (ej: ["*auth*", "*crypto*"]).
    """
    if settings is None:
        settings = load_settings()

    # Try to use explicitly defined patterns first
    patterns = settings.get("critical_patterns", [])
    if patterns:
        return patterns

    # Fallback: generate from critical nodes
    nodes = get_critical_nodes(settings)
    return [f"*{node}*" for node in nodes]
