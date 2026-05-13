"""
Constantes del Asistente.

Valores inmutables que definen limites, defaults
y parametros operativos del sistema.
"""

# ─── Identidad ────────────────────────────────────────────────

APP_NAME: str = "Zenic-Agents"
APP_VERSION: str = "1.0.0"

# ─── Red ──────────────────────────────────────────────────────

DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 5000

# ─── Sesiones ─────────────────────────────────────────────────

SESSION_TIMEOUT_SECONDS: int = 1800     # 30 minutos de inactividad
MAX_SESSIONS: int = 100                 # Maximo de sesiones simultaneas
MAX_MESSAGES_PER_SESSION: int = 200     # Maximo mensajes por sesion

# ─── Contexto ─────────────────────────────────────────────────

MAX_CONTEXT_TOKENS: int = 4000          # Tokens maximos en ventana de contexto
CONTEXT_RESERVE_SYSTEM: int = 500       # Reservados para system prompt
CONTEXT_RESERVE_RESPONSE: int = 1000    # Reservados para respuesta

# ─── Streaming ────────────────────────────────────────────────

STREAMING_CHUNK_SIZE: int = 50          # Caracteres por chunk
STREAMING_DELAY_MS: int = 20            # Delay entre chunks (ms)

# ─── Rate Limiting ────────────────────────────────────────────

RATE_LIMIT_RPM: int = 60               # Requests por minuto por defecto
RATE_LIMIT_BURST: int = 10             # Burst size

# ─── Salud ────────────────────────────────────────────────────

HEALTH_CHECK_INTERVAL_SECONDS: int = 30 # Intervalo de health check

# ─── Personalidad ─────────────────────────────────────────────

PERSONALITY_DEFAULT: str = "zenic"      # Personalidad por defecto

# ─── Memoria ──────────────────────────────────────────────────

MEMORY_IMPORTANCE_THRESHOLD: float = 0.3   # Umbral para guardar en LTM
MEMORY_MAX_WORKING: int = 50               # Max entradas en working memory
MEMORY_MAX_LONG_TERM: int = 500            # Max entradas en long-term memory
MEMORY_CACHE_TTL_SECONDS: int = 3600       # TTL del cache semantico (1h)

# ─── Tools ────────────────────────────────────────────────────

TOOL_EXECUTION_TIMEOUT: float = 30.0      # Timeout para tools (segundos)
TOOL_MAX_CONCURRENT: int = 3              # Max tools ejecutandose simultaneamente

# ─── Logging ──────────────────────────────────────────────────

LOG_LEVEL_DEFAULT: str = "INFO"
LOG_FORMAT: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_MAX_BYTES: int = 10_485_760           # 10MB
LOG_BACKUP_COUNT: int = 3

# ─── Conversacion (Fase 2) ────────────────────────────────────

CONVERSATION_MAX_HISTORY: int = 100        # Max turnos en historial
CONVERSATION_TOPIC_STALE_SECONDS: float = 600.0  # 10 min sin mencion = stale
CONVERSATION_SUMMARY_MIN_MESSAGES: int = 6  # Min mensajes para resumir
CONVERSATION_SUMMARY_MAX_LENGTH: int = 500  # Max chars del resumen

# ─── Conocimiento (Fase 2) ────────────────────────────────────

KNOWLEDGE_MAX_ENTRIES: int = 1000          # Max entradas en knowledge base
KNOWLEDGE_MAX_RESULTS: int = 5             # Max resultados de busqueda

# ─── Contexto Builder (Fase 2) ───────────────────────────────

CONTEXT_MAX_MEMORY_ENTRIES: int = 5        # Max entradas de memoria en contexto
CONTEXT_MAX_KNOWLEDGE_ENTRIES: int = 3     # Max entradas de conocimiento en contexto
