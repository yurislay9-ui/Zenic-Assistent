<div align="center">

# ZENIC-AGENTS v1.0.0

### Plataforma de Asistencia Empresarial Inteligente — DAG Core + SNA + Blueprints + Defense in Depth

**Motor de agentes con DAG de 59 nodos, 9 Executors, Sistema Nervioso Autonomo,
Blueprints Certificados, Multi-Rol Colaborativo y Capa Conversacional.**
Funciona en **Android/Termux** sin GPU. IA solo como arbitro binario YES/NO.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Agents](https://img.shields.io/badge/Agents-48%20%7C%209%20Layers-orange.svg)](src/core/agents_v2/)
[![DAG Nodes](https://img.shields.io/badge/DAG_Nodes-59%20%7C%203_Parallel_Groups-critical.svg)](src/core/dag_parts/unified_definition.py)
[![Executors](https://img.shields.io/badge/Executors-9%20Types-blueviolet.svg)](src/core/executors/)
[![SNA](https://img.shields.io/badge/SNA-Monitors%20%7C%20Scheduler-yellow.svg)](src/core/sna/)
[![Tests](https://img.shields.io/badge/Tests-381%20passed-brightgreen.svg)](tests/)

</div>

---

## Filosofia

> **Un agente = una funcion. Sin excepciones.**

Zenic-Agents es la evolucion unificada de Zenic-Agents y Zenic-Asistente en una sola plataforma cohesiva. El sistema sigue el Principio de Responsabilidad Unica (SRP) con **48 agentes atomicos**, cada uno con exactamente una responsabilidad, un fallback determinista, y proteccion con circuit breaker, retry y auditoria. El orquestador unificado (Unified DAG) maneja **59 nodos** con ejecucion paralela via `asyncio.gather()`, comunicacion inter-agente por **SharedMemoryBus** con respaldo SQLite WAL, y cache de ruteo LRU con TTL.

### 6 Invariantes Arquitectonicos

| # | Invariante | Regla |
|---|-----------|-------|
| 1 | **No LLM directo** | Ningun agente llama al LLM directamente. Todo va por VerdictEngine. |
| 2 | **Solo SI/NO** | El LLM solo puede responder YES o NO. Cualquier otra respuesta = NO. |
| 3 | **Fallback determinista** | Cada agente funciona sin IA. El sistema opera 100% sin modelo. |
| 4 | **Sin duplicacion** | Cada funcion existe en exactamente un agente. Duplicar = error de diseno. |
| 5 | **Auditoria total** | Cada llamada y decision tiene registro con evidencia. |
| 6 | **Veto de seguridad** | Si SecurityScanner dice NO, es NO. Sin override posible. |

---

## Estado del Proyecto — 8 Fases (7 Completadas)

| Fase | Nombre | Estado | Descripcion |
|------|--------|--------|-------------|
| **0** | Fundacion Rust + PyO3 | Pendiente | Core en Rust con FFI a Python |
| **1** | Core Rust: Safety Gate + DAG | Parcial | DAG Core 59 nodos en Python, Rust pendiente |
| **2** | Capa Conversacional | Completo | Session manager, LLM translator, adapters Telegram/Discord |
| **3** | 9 Executors Directos | Completo | email, http, db, file, notification, schedule, transform, webhook, base |
| **4** | Sistema Nervioso Autonomo | Completo | Scheduler, monitores LIVIANOS/MEDIANOS/PESADOS, umbrales |
| **5** | Blueprints Certificados | Completo | Schema, Loader, Composer, Onboarding, SDK, ECDSA signing |
| **6** | Multi-Rol + Seguridad | Completo | Roles granulares, cadenas aprobacion, Defense in Depth 6 capas |
| **7** | Frontend Web + Billing | Completo | HTMX+Alpine.js, Stripe billing, CI/CD GitHub Actions |

### Componentes Implementados

| Componente | Ubicacion | Estado |
|---|---|---|
| DAG Core 59 nodos | `src/core/dag_parts/` | Completo |
| VerdictEngine (AI binario) | `src/core/agents_v2/verdict/` | Completo |
| Safety Gate | `src/core/agents_v2/validation/` | Completo |
| 9 Executors | `src/core/executors/` | Completo |
| Capa Conversacional | `src/core/conversational/` | Completo |
| SNA (Sistema Nervioso) | `src/core/sna/` | Completo |
| Blueprints Certificados | `src/core/blueprints/` | Completo |
| Multi-Rol + Aprobacion | `src/core/approval/` + `src/core/auth_parts/` | Completo |
| Defense in Depth (6 capas) | `src/core/defense/` | Completo |
| Licenciamiento ECDSA | `src/core/license/` | Completo |
| Modo Degradado | `src/core/degraded_mode/` | Completo |
| Billing (Stripe) | `src/core/billing/` | Completo |
| Frontend HTMX+Alpine.js | `src/server/templates/` + `src/server/static/` | Completo |
| CI/CD GitHub Actions | `.github/workflows/build.yml` | Completo |
| SharedMemoryBus | `src/core/shared/shared_memory_bus.py` | Completo |
| FastConnectionPool | `src/core/shared/fast_connection_pool.py` | Completo |
| Observabilidad | `src/core/observability/` | Completo |
| Distribucion (SAGA) | `src/core/distributed/saga_coordinator.py` | Completo |
| Patrones de Resiliencia | `src/core/patterns/` (18 modulos) | Completo |
| API OpenAI-compatible | `src/server/fastapi_app.py` | Completo |
| Docker/Deploy | `Dockerfile` + `docker-compose.yml` | Completo |

---

## Arquitectura del Unified DAG Orchestrator

```
USER INPUT
    |
    v
+------------------------------------------------------------------+
|  ENTRY: CACHE_CHECK -> BILINGUAL_ROUTE -> INTENT_CLASSIFY           |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 1: UNDERSTAND (100% Determinista)                          |
|  [ENTITY_EXTRACT || TARGET_RESOLVE]  <- PARALELO (asyncio.gather) |
|                     |                                              |
|                     v                                              |
|              CRITICALITY_SCORE                                     |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 2: CONTEXT (100% Determinista)                             |
|  [MEMORY_COLLECT || SEMANTIC_PREP]  <- PARALELO (asyncio.gather)  |
|                     |                                              |
|                     v                                              |
|  RELEVANCE_SCORE -> CONTEXT_COMPRESS -> CONTEXT_PREFETCH           |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  ROUTING: AST_ANALYZE -> THEOREM_CACHE -> ROUTE -> ROUTE_DECISION |
|  ROUTE_DECISION -> {code | biz | auto | reason | high_crit |      |
|                    visual | abortive}                              |
+------------------------------------------------------------------+
    |       |        |       |        |
    v       v        v       v        v
+--------+ +------+ +-----+ +------+ +--------+
| CODE   | | BIZ  | |AUTO | |REASON| |SOLVER  |
| PATH   | | PATH | |PATH | | PATH | |VERIFY  |
+--------+ +------+ +-----+ +------+ +--------+
    |       |        |       |        |
    +-------+--------+-------+--------+
            |
            v
+------------------------------------------------------------------+
|  PHASE 4: VALIDATE (100% Determinista)                            |
|  SECURITY_SCAN -> SYNTAX_VALIDATE -> RISK_CALC -> FIX_SUGGEST     |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 5: VERDICT (IA Solo Si Necesario)                          |
|  EVIDENCE_COLLECT -> CONSENSUS_RESOLVE -> VERDICT                 |
|  Consenso >= HIGH -> Decision (Sin IA)                            |
|  Consenso < HIGH  -> A43 VerdictEngine (Qwen: YES/NO)            |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 6: SANDBOX -> LEDGER_COMMIT/ROLLBACK -> THEOREM_SAVE       |
|           -> MEMORY_SAVE -> DONE                                  |
+------------------------------------------------------------------+
```

---

## Arquitectura de 9 Capas — 48 Agentes SRP

```
 CAPA 1: UNDERSTANDING          CAPA 2: MEMORY & CONTEXT
 A01 IntentClassifier           A05 MemoryCollector
 A02 EntityExtractor            A06 RelevanceScorer
 A03 TargetResolver             A07 ContextCompressor
 A04 CriticalityScorer          A08 ContextPrefetcher
 A48 BilingualRouter

 CAPA 3: BUSINESS               CAPA 4: CODE OPS
 A09 InvoiceProcessor           A17 CodeGenerator
 A10 InventoryManager           A18 CodeRefactorer
 A11 CRMPipeline                A19 CodeOptimizer
 A12 TaskScheduler              A20 CodeFixer
 A13 ReportGenerator            A21 ProjectScaffolder
 A14 NotificationDispatcher     A22 DefensiveInjector
 A15 DataAnalyzer
 A16 OperationRouter

 CAPA 5: VALIDATION             CAPA 6: AUTOMATION
 A23 SecurityScanner            A29 TriggerInferrer
 A24 SyntaxValidator            A30 ActionInferrer
 A25 ChainValidator             A31 ScheduleParser
 A26 ConfigValidator            A32 ConditionExtractor
 A27 RiskCalculator            A33 AutomationNamer
 A28 FixSuggester              A34 WorkflowSerializer

 CAPA 7: REASONING              CAPA 8: VERDICT (AI Arbiter)
 A35 ProblemDetector            A40 DeterministicPipeline
 A36 StepDecomposer             A41 EvidenceCollector
 A37 TemplateReasoner           A42 ConsensusResolver
 A38 ConfidenceEstimator        A43 VerdictEngine <- UNICO punto con IA
 A39 ConclusionExtractor

 CAPA 9: INFRASTRUCTURE
 A44 AgentRunner
 A45 HealthMonitor
 A46 AuditLogger
 A47 CircuitBreakerManager
```

---

## Capa Conversacional (Fase 2)

La capa conversacional unificada en `src/core/conversational/` proporciona interaccion multi-turno:

| Modulo | Descripcion |
|--------|-------------|
| `conversation/` | Manager, State, Summarizer, Turn Tracker |
| `engine_parts/` | Response Generator, Formatter, Intent Classifier |
| `events/` | Event Bus + Event Types |
| `input/` | Parser, Enricher, Sanitizer |
| `knowledge/` | Knowledge Base |
| `memory/` | Long-term, Short-term, Working Memory, Manager, Scorer |
| `routing/` | Router, Pipeline Selector, Fallback Chain, Intent Engine |
| `tools/` | Registry, Manager, Permissions, Executor |
| `config/` | Environment + Constants |
| `types/` | Memory, Events, Intent, Personality, Response, Tool Use, Session |
| `zenic_bridge.py` | Bridge al motor DAG Core |
| `session_manager.py` | Gestion de sesiones con estado estructurado |
| `personality_manager.py` | Personalidad y tono del asistente |

---

## Sistema Nervioso Autonomo (Fase 4)

Monitoreo proactivo sin solicitud del usuario:

| Clasificacion | Ejemplos | Intervalo |
|---|---|---|
| **LIVIANOS** | Stock bajo, factura vencida, cita manana | 5-15 min |
| **MEDIANOS** | Tendencia ventas, ratio conversion CRM | 30-60 min |
| **PESADOS** | Analisis multi-fuente, proyecciones demanda | 2-6 horas |

Flujo: SNA detecta anomalia -> POST al DAG -> DAG valida -> notifica via Executor

---

## Blueprints Certificados (Fase 5)

De templates YAML fijos a Blueprints modulares componibles:

- **Schema**: Metadata + schema DB + reglas negocio + monitores + acciones
- **Loader**: Carga Blueprints firmados (YAML/JSON)
- **Composer**: Composicion automatica (merge de schemas, reglas, monitores)
- **Onboarding**: Seleccion de Blueprints durante setup + auto-configuracion
- **SDK**: API para partners creen Blueprints custom
- **ECDSA**: Firma criptografica de Blueprints certificados

---

## Defense in Depth (6 Capas - Fase 6)

| Capa | Mecanismo |
|------|-----------|
| 1 | mlock + anti-debug + anti-ptrace (Rust) |
| 2 | Nuitka compilation + Rust binary |
| 3 | SQLCipher + Fernet + PBKDF2 (Rust) |
| 4 | Hash chain integrity + cross-verification |
| 5 | Licenciamiento ECDSA (Rust) |
| 6 | Server-side secrets (20% logica remota) |

---

## Hardware y Modelo IA

| Parametro | Valor |
|-----------|-------|
| Dispositivo objetivo | Xiaomi Redmi 12R Pro |
| Procesador | MediaTek Dimensity 6100+ |
| RAM | 12GB + 8GB virtual (swap) |
| GPU | No requerida (CPU-only) |
| Modelo IA | Qwen3-0.6B Q4_K_M (378MB) |
| Motor de inferencia | llama-cpp-python |
| Tiempo por inferencia | ~2-5s (CPU) |
| RAM idle | ~50 MB |

---

## Instalacion

### Requisitos

- **Python**: 3.10+
- **RAM**: Minimo 4GB (8GB+ recomendado)
- **Disco**: ~500MB para modelo + dependencias
- **Opcional**: Z3 Solver, fastembed, Textual (TUI)

### Instalacion Rapida

```bash
# Clonar el repositorio
git clone https://github.com/yurislay9-ui/Zenic-Agents.git
cd Zenic-Agents

# Instalar dependencias core
pip install -r requirements.txt

# Opcional: Z3 para verificacion formal
pip install z3-solver

# Opcional: Embeddings semanticos
pip install fastembed

# Opcional: Interfaz grafica
pip install textual

# Descargar modelo IA
mkdir -p models
# Colocar qwen3-0.6b-q4_k_m.gguf en models/
```

### Instalacion en Android/Termux

```bash
bash scripts/install_termux.sh

# O manualmente:
pkg install python python-pip
pip install -r requirements.txt
```

---

## Uso

### Modo Headless (CLI)

```bash
# Servidor estandar
python main_headless.py --port 5000 --ram-limit 2048

# Servidor FastAPI (SaaS)
python main_headless.py --server fastapi --auth

# Modo daemon (background)
python main_headless.py --daemon
```

### Interfaz Textual (TUI)

```bash
pip install textual
python main.py
```

### Modo Asistente (Conversacional)

```bash
python main_conversational.py
```

### API OpenAI-Compatible

```http
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "zenic-agents",
  "messages": [
    {"role": "user", "content": "crear modulo auth.py con JWT"}
  ],
  "temperature": 0.15,
  "max_tokens": 600,
  "stream": false
}
```

---

## API Endpoints

### Core

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/v1/chat/completions` | Chat OpenAI-compatible (SSE streaming soportado) |
| GET | `/v1/models` | Listar modelos disponibles |
| GET | `/health` | Liveness probe (K8s-style) |
| GET | `/ready` | Readiness probe |

### Autenticacion

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/v1/auth/register` | Registro de usuario |
| POST | `/v1/auth/login` | Login -> JWT tokens |
| POST | `/v1/auth/refresh` | Renovar access token |
| POST | `/v1/auth/logout` | Logout con blacklisting |
| POST | `/v1/auth/api-keys` | Crear API key |

### Multi-Tenancy

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET/POST | `/v1/tenants` | Listar/crear tenants |
| GET/PATCH/DELETE | `/v1/tenants/{id}` | Gestionar tenant |
| GET | `/v1/tenants/{id}/usage` | Uso y quotas |
| POST | `/v1/tenants/{id}/assign/{user_id}` | Asignar usuario |

**Planes**: Free (10 RPM) / Pro (60 RPM) / Enterprise (200 RPM)

### Generacion & Razonamiento

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/v1/generate/app` | Generar aplicacion completa |
| POST | `/v1/generate/automation` | Generar automatizacion |
| POST | `/v1/think` | ThinkingEngine |
| POST | `/v1/reason` | Razonamiento avanzado |
| POST | `/v1/chain/validate` | Validar cadena logica |
| POST | `/v1/design/schema` | Disenar esquema de BD |

### SNA & Blueprints

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/v1/sna/monitors` | Listar monitores activos |
| POST | `/v1/sna/monitors` | Crear monitor |
| GET | `/v1/blueprints` | Listar Blueprints certificados |
| POST | `/v1/blueprints/compose` | Componer Blueprints |

### Cluster & Observabilidad

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/v1/cluster/nodes` | Nodos del cluster |
| POST | `/v1/saga/start` | Iniciar saga workflow |
| GET | `/metrics` | Prometheus metrics |
| GET | `/v1/audit/events` | Query audit events |

---

## Estructura del Proyecto

```
Zenic-Agents/
├── main.py                          # Interfaz Textual (TUI)
├── main_headless.py                 # Servidor CLI
├── main_conversational.py           # Modo conversacional
├── pyproject.toml                   # Configuracion del proyecto
├── requirements.txt                 # Dependencias
├── docs/                            # Documentacion y whitepaper
│
├── src/
│   ├── config/                      # Configuracion (YAML + loader)
│   ├── core/
│   │   ├── agents_v2/               # 48 Agentes SRP (9 capas)
│   │   ├── dag_parts/               # Unified DAG Orchestrator (59 nodos)
│   │   ├── conversational/          # Capa conversacional multi-turno
│   │   │   ├── conversation/        # Manager, State, Summarizer
│   │   │   ├── engine_parts/        # Response Generator, Intent Classifier
│   │   │   ├── events/              # Event Bus + Types
│   │   │   ├── input/               # Parser, Enricher, Sanitizer
│   │   │   ├── knowledge/           # Knowledge Base
│   │   │   ├── memory/              # Long/Short/Working Memory
│   │   │   ├── routing/             # Router, Pipeline, Fallback
│   │   │   ├── tools/               # Registry, Permissions, Executor
│   │   │   ├── types/               # Tipos compartidos
│   │   │   ├── config/              # Config del asistente
│   │   │   ├── utils/               # Logger, Helpers, Validators
│   │   │   ├── zenic_bridge.py      # Bridge al motor DAG
│   │   │   └── session_manager.py   # Gestion de sesiones
│   │   │
│   │   ├── executors/               # 9 Executors (email, http, db, etc.)
│   │   ├── sna/                     # Sistema Nervioso Autonomo
│   │   │   ├── scheduler.py         # Scheduler de monitores
│   │   │   ├── monitores/           # LIVIANOS, MEDIANOS, PESADOS
│   │   │   └── thresholds.py        # Umbrales configurables
│   │   │
│   │   ├── blueprints/              # Blueprints Certificados
│   │   │   ├── schema.py            # Blueprint Schema
│   │   │   ├── loader.py            # Loader & Composer
│   │   │   ├── onboarding.py        # Sistema de Onboarding
│   │   │   └── sdk.py              # SDK para partners
│   │   │
│   │   ├── approval/                # Cadenas de aprobacion
│   │   ├── auth_parts/              # JWT + RBAC + Multi-Rol
│   │   ├── billing/                 # Stripe + Trial + Webhooks
│   │   ├── defense/                 # Defense in Depth (6 capas)
│   │   ├── degraded_mode/           # Modo degradado post-trial
│   │   ├── license/                 # ECDSA + Hardware binding
│   │   ├── shared/                  # SharedMemoryBus + FastPool + Z3
│   │   ├── distributed/             # SAGA + Circuit Breaker
│   │   ├── observability/           # Tracing + Metrics + Health
│   │   ├── patterns/                # Design patterns (18 modulos)
│   │   ├── tenant/                  # Multi-tenancy
│   │   └── ...                      # 40+ sub-modulos mas
│   │
│   ├── server/                      # FastAPI HTTP server
│   │   ├── fastapi_app.py           # App principal
│   │   ├── templates/               # Jinja2 (HTMX)
│   │   ├── static/                  # CSS + JS (Alpine.js, Chart.js)
│   │   ├── htmx_routes/             # Rutas HTMX modulares
│   │   └── ...
│   │
│   └── templates/                   # YAML niche templates
│
├── tests/                           # 381+ tests
│   ├── unit/
│   └── integration/
│
├── .github/workflows/               # CI/CD (Rust+PyO3+Nuitka)
├── deploy/                          # Docker, nginx, systemd
├── rust/                            # Rust core (Phase 0 - pendiente)
└── scripts/                         # Install + deploy scripts
```

---

## Conectar con Cline/Aide/OpenCode

```json
{
  "apiKey": "your-api-key",
  "baseURL": "http://YOUR_IP:5000/v1",
  "model": "zenic-agents"
}
```

---

## Testing

```bash
# Ejecutar tests de agentes V18 (capas 5-9)
pytest tests/unit/test_layer5_validation.py tests/unit/test_layer6_automation.py \
       tests/unit/test_layer7_reasoning.py tests/unit/test_layer8_verdict.py \
       tests/unit/test_layer9_infrastructure.py -v

# Ejecutar todos los tests
pytest tests/ -v

# Con cobertura
pytest tests/ --cov=src --cov-report=term-missing
```

---

## Licencia

MIT License — ver [LICENSE](LICENSE) para detalles.

---

<div align="center">

**ZENIC-AGENTS** — 48 Agentes SRP | DAG 59 Nodos | 9 Executors | SNA | Blueprints | Defense in Depth | Conversacional

</div>
