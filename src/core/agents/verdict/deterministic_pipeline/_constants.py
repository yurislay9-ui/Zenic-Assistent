"""
Deterministic Pipeline Constants — Lookup tables and catalogs.

Contains all static data structures used by the 7 deterministic tasks:
  1. EXT_LANG_MAP: File extension → language mapping
  2. OP_KEYWORDS: Operation classification keywords (EN + ES)
  3. GOAL_KEYWORDS: Goal classification keywords (EN + ES)
  4. PATTERN_HEURISTICS: Pattern suggestion heuristics
  5. PATTERN_LIBRARY: Code template library
  6. VIOLATION_CATALOG: Security violation explanations
  7. GAP_DEFAULTS: Template gap fill defaults
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# EXTENSION → LANGUAGE MAPPING
# ──────────────────────────────────────────────────────────────

EXT_LANG_MAP: dict[str, str] = {
    ".py": "python", ".kt": "kotlin", ".go": "go",
    ".js": "javascript", ".ts": "typescript", ".java": "java",
    ".rs": "rust", ".rb": "ruby", ".cpp": "cpp", ".c": "c",
    ".h": "c", ".hpp": "cpp", ".swift": "swift", ".scala": "scala",
}

# ──────────────────────────────────────────────────────────────
# OPERATION KEYWORDS (Task 1: classify_intent)
# ──────────────────────────────────────────────────────────────

OP_KEYWORDS: dict[str, list[str]] = {
    "CREATE": [
        "create", "build", "make", "generate", "add", "implement",
        "desarrollar", "crear", "construir", "generar", "agregar", "implementar",
    ],
    "REFACTOR": [
        "refactor", "restructure", "reorganize", "clean", "simplify",
        "refactorizar", "reestructurar", "reorganizar", "limpiar", "simplificar",
    ],
    "DELETE": [
        "delete", "remove", "drop", "clear", "purge",
        "eliminar", "borrar", "quitar", "limpiar",
    ],
    "SEARCH": [
        "search", "find", "locate", "query", "look for",
        "buscar", "encontrar", "localizar", "consultar",
    ],
    "ANALYZE": [
        "analyze", "review", "audit", "inspect", "evaluate",
        "analizar", "revisar", "auditar", "inspeccionar", "evaluar",
    ],
    "EXPLAIN": [
        "explain", "describe", "document", "clarify", "understand",
        "explicar", "describir", "documentar", "aclarar", "entender",
    ],
    "DEBUG": [
        "debug", "fix", "repair", "troubleshoot", "diagnose",
        "depurar", "arreglar", "reparar", "solucionar", "diagnosticar",
    ],
    "OPTIMIZE": [
        "optimize", "improve", "enhance", "speed up", "accelerate",
        "optimizar", "mejorar", "acelerar", "rendimiento",
    ],
}

GOAL_KEYWORDS: dict[str, list[str]] = {
    "FEATURE_ADD": [
        "feature", "functionality", "capability", "new", "extend",
        "característica", "funcionalidad", "capacidad", "nuevo", "extender",
    ],
    "BUG_FIX": [
        "bug", "error", "issue", "problem", "crash", "fail",
        "error", "problema", "fallo", "cuelgue", "falla",
    ],
    "SECURITY_HARDEN": [
        "security", "vulnerability", "auth", "protect", "sanitize",
        "seguridad", "vulnerabilidad", "proteger", "sanitizar",
    ],
    "PERFORMANCE": [
        "performance", "speed", "latency", "throughput", "efficiency",
        "rendimiento", "velocidad", "latencia", "eficiencia",
    ],
    "COMPLEXITY_REDUCTION": [
        "simplify", "reduce", "streamline", "clean", "refactor",
        "simplificar", "reducir", "limpiar",
    ],
    "MODERN_PATTERN": [
        "modernize", "update", "upgrade", "migrate", "latest",
        "modernizar", "actualizar", "migrar",
    ],
    "READABILITY": [
        "readable", "clear", "document", "comment", "naming",
        "legible", "claro", "documentar", "comentar",
    ],
}

# ──────────────────────────────────────────────────────────────
# PATTERN HEURISTICS (Task 3: suggest_pattern)
# ──────────────────────────────────────────────────────────────

PATTERN_HEURISTICS: list[tuple] = [
    (["async", "await", "coroutine", "asincrono"], "async_await"),
    (["validate", "validar", "check", "verify", "verificar"], "validator"),
    (["repository", "repo", "database", "db", "base de datos"], "repository"),
    (["factory", "create", "creator", "fabrica"], "factory"),
    (["middleware", "interceptor", "pipeline"], "middleware"),
    (["observer", "subscribe", "event", "listen", "escuchar"], "observer"),
    (["security", "auth", "login", "token", "seguridad"], "security"),
    (["cache", "memoize", "store", "cachear"], "cache"),
    (["singleton", "single", "unique", "unico"], "singleton"),
]

# ──────────────────────────────────────────────────────────────
# PATTERN LIBRARY (Task 5: generate_pattern)
# ──────────────────────────────────────────────────────────────

PATTERN_LIBRARY: dict[str, dict[str, str]] = {
    "python": {
        "async_await": "async def {name}({params}):\n    result = await {operation}({params})\n    return result\n",
        "validator": "def {name}(data: dict) -> bool:\n    required = {required_fields}\n    return all(k in data for k in required)\n",
        "repository": "class {class_name}:\n    def __init__(self, db):\n        self.db = db\n    def get_by_id(self, id: str):\n        return self.db.query(id)\n",
        "factory": "def create_{name}(type_: str):\n    handlers = {handler_map}\n    return handlers.get(type_, DefaultHandler)\n",
        "middleware": "def {name}(func):\n    def wrapper(*args, **kwargs):\n        pre_process(*args)\n        result = func(*args, **kwargs)\n        post_process(result)\n        return result\n    return wrapper\n",
        "observer": "class {class_name}:\n    def __init__(self):\n        self._observers = []\n    def subscribe(self, observer):\n        self._observers.append(observer)\n    def notify(self, event):\n        for obs in self._observers:\n            obs.on_event(event)\n",
        "security": "import hashlib, secrets\n\ndef hash_password(password: str) -> str:\n    salt = secrets.token_hex(16)\n    return hashlib.sha256((salt + password).encode()).hexdigest()\n",
        "cache": "from functools import lru_cache\n\n@lru_cache(maxsize=128)\ndef {name}(key):\n    return expensive_lookup(key)\n",
        "singleton": "class {class_name}:\n    _instance = None\n    def __new__(cls):\n        if cls._instance is None:\n            cls._instance = super().__new__(cls)\n        return cls._instance\n",
        "default": "def {name}(data):\n    \"\"\"Generated by ZENIC-AGENTS v1\"\"\"\n    return data\n",
    },
    "javascript": {
        "async_await": "async function {name}({params}) {\n    const result = await {operation}({params});\n    return result;\n}\n",
        "validator": "function {name}(data) {\n    const required = {required_fields};\n    return required.every(k => k in data);\n}\n",
        "default": "function {name}(data) {\n    return data;\n}\n",
    },
    "typescript": {
        "default": "function {name}(data: any): any {\n    return data;\n}\n",
    },
}

# ──────────────────────────────────────────────────────────────
# VIOLATION CATALOG (Task 6: explain_violation)
# ──────────────────────────────────────────────────────────────

VIOLATION_CATALOG: dict[str, str] = {
    "exec_call": "Use of exec() allows arbitrary code execution, which is a critical security risk.",
    "eval_call": "Use of eval() allows arbitrary code execution, which is a critical security risk.",
    "import_call": "Dynamic import via __import__() can load untrusted modules at runtime.",
    "os_system": "os.system() executes shell commands, vulnerable to injection attacks.",
    "subprocess_call": "subprocess calls can execute arbitrary system commands.",
    "pickle_load": "pickle.loads() can deserialize malicious objects leading to RCE.",
    "yaml_unsafe": "yaml.load() without SafeLoader can execute arbitrary Python code.",
    "sensitive_file": "Access to sensitive system files (/etc, /proc, /sys) detected.",
    "rm_rf": "Dangerous rm -rf command detected, can destroy entire filesystems.",
    "socket_raw": "Raw socket creation detected, may indicate network-level exploits.",
    "null_pointer": "Potential null/None dereference detected.",
    "type_mismatch": "Type mismatch detected in function call.",
    "unreachable": "Unreachable code detected after return statement.",
    "unused_import": "Unused import detected.",
}

# Gap defaults for template filling (Task 4)
GAP_DEFAULTS: dict[str, str] = {
    "NAME": "generated",
    "CLASS_NAME": "GeneratedClass",
    "FUNC_NAME": "generated_function",
    "RETURN_TYPE": "Any",
    "PARAMS": "self",
    "BODY": "pass",
    "DOCSTRING": "Generated by ZENIC-AGENTS v1",
    "IMPORT": "import os",
    "VAR_NAME": "result",
    "TYPE": "str",
    "OPERATION": "process",
    "REQUIRED_FIELDS": "['id', 'name']",
    "HANDLER_MAP": "{}",
}
