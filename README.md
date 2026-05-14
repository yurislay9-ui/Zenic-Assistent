<div align="center">

# ZENIC-AGENTS v3.0.0

### Plataforma de Asistencia Empresarial Inteligente

**Motor de agentes con DAG de 59 nodos, 9 Executors, Sistema Nervioso Autonomo,
Blueprints Certificados Dinamicos, Multi-Rol Colaborativo y Capa Conversacional.**

Funciona en **Android/Termux** sin GPU. IA solo como arbitro binario YES/NO.
Core critico compilado en **Rust** con bindings **PyO3**.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Rust 1.85+](https://img.shields.io/badge/Rust-1.85%2B-orange.svg)](https://www.rust-lang.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Agents](https://img.shields.io/badge/Agents-42%20%7C%209%20Layers-orange.svg)](src/core/agents_v2/)
[![Niches](https://img.shields.io/badge/Niches-24%20Compiled%20Rust-critical.svg)](zenic-v2/zenic-pybridge/src/catalog.rs)
[![PyO3](https://img.shields.io/badge/PyO3-21%20Rust%20Modules-blueviolet.svg)](zenic-v2/zenic-pybridge/src/lib.rs)

</div>

---

## Filosofia

> **Un agente = una funcion. Sin excepciones.**

Zenic-Agents es una **plataforma de asistencia empresarial** que opera bajo el Principio de Responsabilidad Unica (SRP). Cada uno de sus **42 agentes atomicos** tiene exactamente una responsabilidad, un fallback determinista, y proteccion con circuit breaker, retry y auditoria completa. El orquestador unificado (Unified DAG) maneja **59 nodos** con ejecucion paralela via `asyncio.gather()`, comunicacion inter-agente por **SharedMemoryBus** con respaldo SQLite WAL, y cache de ruteo LRU con TTL.

> **Nota**: Zenic es un **agente asistente**, NO un generador de codigos. Los modulos de generacion de codigo (CodeGenerator, AppGenerator, TemplateEngine, FractalGenerator, SchemaDesigner, CodeAgent) fueron eliminados en v3.0.0.

El core de alto rendimiento esta implementado en **Rust** y expuesto a Python via **PyO3**, cubriendo criptografia, hashing, base de datos cifrada, auditoria forense, rollback atomico, event bus, simulacion DAG, prediccion de riesgo, licenciamiento, nichos, ingesta de documentos, extraccion de campos, completado de plantillas, certificacion de blueprints y pipeline E2E completo.

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

## Estado del Proyecto

| Fase | Nombre | Estado | Descripcion |
|------|--------|--------|-------------|
| **1** | Core Rust + PyO3 | Completo | 21 modulos Rust via PyO3: crypto, hash, db, forensic, rollback, eventbus, simulation, risk, bus, safety_gate, license, niche, catalog, template, ingest, extractor, completer, certifier, safety_gate_extended, e2e_pipeline |
| **2** | Capa Conversacional | Completo | Session manager, LLM translator, adapters Telegram/Discord, memory, routing, tools |
| **3** | 9 Executors Directos | Completo | email, http, db, file, notification, schedule, transform, webhook, base |
| **4** | Sistema Nervioso Autonomo | Completo | Scheduler, monitores LIVIANOS/MEDIANOS/PESADOS, umbrales |
| **5** | Blueprints Certificados | Completo | Schema, Loader, Composer, Onboarding, SDK, ECDSA signing |
| **6** | Nichos Dinamicos + Seguridad | Completo | 24 nichos compilados en Rust, generacion dinamica de YAML desde documentos del usuario, Q&A interactivo, certificacion, safety extendido |
| **7** | Frontend Web + Billing | Completo | HTMX+Alpine.js, Stripe billing, CI/CD GitHub Actions |

### zenic-v2 Workspace (Rust unificado — 11 crates)

| Crate | Estado | Descripcion |
|-------|--------|-------------|
| `zenic-proto` | Completo | Tipos base, IDs, dominio, node_types, serializacion binaria |
| `zenic-graph` | Completo | Grafo DAG, subgrafos, supernodos, catalogo, descriptores |
| `zenic-runtime` | Completo | Ejecutor, scheduler, contexto, memoria, loader |
| `zenic-flow` | Completo | Motor de flujo, steps, checkpoints, retry, compensacion |
| `zenic-policy` | Completo | Motor de politicas, roles, permisos, reglas, auditoria |
| `zenic-safety` | Completo | Veredictos, compliance, sensitividad, reglas de dominio |
| `zenic-core` | Completo | Orquestador, router, sesiones, configuracion |
| `zenic-pybridge` | Completo | Puente PyO3 — expone Rust a Python como `_zenic_native` (21 modulos) |
| `zenic-ffi` | Stub | FFI bindings para integracion externa |
| `zenic-bench` | Stub | Benchmarks de rendimiento |
| `zenic-tests` | Stub | Tests de integracion del workspace |

---

## Arquitectura General

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
|  ROUTE_DECISION -> {biz | auto | reason | high_crit | abortive}  |
+------------------------------------------------------------------+
    |       |        |        |
    v       v        v        v
+------+ +-----+ +------+ +--------+
| BIZ  | |AUTO | |REASON| |SOLVER  |
| PATH | |PATH | | PATH | |VERIFY  |
+------+ +-----+ +------+ +--------+
    |       |        |        |
    +-------+--------+--------+
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
|  Consenso < HIGH  -> VerdictEngine (Qwen: YES/NO)                |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 6: SANDBOX -> LEDGER_COMMIT/ROLLBACK -> THEOREM_SAVE       |
|           -> MEMORY_SAVE -> DONE                                  |
+------------------------------------------------------------------+
```

---

## Arquitectura de 9 Capas — 42 Agentes SRP

```
 CAPA 1: UNDERSTANDING          CAPA 2: MEMORY & CONTEXT
 A01 IntentClassifier           A05 MemoryCollector
 A02 EntityExtractor            A06 RelevanceScorer
 A03 TargetResolver             A07 ContextCompressor
 A04 CriticalityScorer          A08 ContextPrefetcher
 A42 BilingualRouter

 CAPA 3: BUSINESS               CAPA 4: VALIDATION
 A09 InvoiceProcessor           A23 SecurityScanner
 A10 InventoryManager           A24 SyntaxValidator
 A11 CRMPipeline                A25 ChainValidator
 A12 TaskScheduler              A26 ConfigValidator
 A13 ReportGenerator            A27 RiskCalculator
 A14 NotificationDispatcher     A28 FixSuggester
 A15 DataAnalyzer
 A16 OperationRouter

 CAPA 5: AUTOMATION             CAPA 6: REASONING
 A29 TriggerInferrer            A35 ProblemDetector
 A30 ActionInferrer             A36 StepDecomposer
 A31 ScheduleParser             A37 TemplateReasoner
 A32 ConditionExtractor         A38 ConfidenceEstimator
 A33 AutomationNamer            A39 ConclusionExtractor
 A34 WorkflowSerializer

 CAPA 7: VERDICT (AI Arbiter)   CAPA 8: INFRASTRUCTURE
 A40 DeterministicPipeline      A44 AgentRunner
 A41 EvidenceCollector          A45 HealthMonitor
 A42 ConsensusResolver          A46 AuditLogger
 A43 VerdictEngine <- UNICO     A47 CircuitBreakerManager
     punto con IA
```

---

## Fase 6: Nichos Dinamicos

La Fase 6 implementa un sistema de nichos de vanguardia donde las plantillas YAML se generan **dinamicamente** a partir de los documentos del usuario, eliminando la necesidad de plantillas preconstruidas.

### Flujo del Pipeline de Nichos

```
1. Usuario selecciona nicho (de los 24 compilados en Rust)
2. Usuario sube documentos (PDF, docs, textos, etc.)
3. Agente especializado genera plantilla YAML desde los documentos
4. Agente identifica campos faltantes y pregunta al usuario
5. Blueprint certificado con firma ECDSA
```

### 24 Nichos Compilados en Rust

| Categoria | Nichos |
|-----------|--------|
| **AI & Machine Learning** | ai_automation, ai_consulting, ai_content_studio |
| **SaaS & Software** | saas_micro, saas_platform, dev_tools |
| **Digital Commerce** | ecommerce_d2c, marketplace_vertical, digital_products |
| **Content & Media** | creator_economy, podcast_monetization, newsletter_media |
| **Finance & Crypto** | defi_analytics, crypto_infrastructure, fintech_embedded |
| **Health & Bio** | healthtech, biotech_data, wellness_digital |
| **Education** | edtech_platform, corporate_training, skill_marketplace |
| **Sustainability** | climate_tech, green_energy, circular_economy |
| **Professional Services** | legal_tech, consulting_platform, hr_tech |

### Modulos Rust de la Fase 6

| Modulo | Descripcion |
|--------|-------------|
| `niche.rs` | Tipos core: NicheDefinition, NicheCategory, TemplateFieldSchema |
| `catalog.rs` | Catalogo estatico compilado de 24 nichos |
| `template.rs` | Generacion, validacion y fill de plantillas YAML |
| `ingest.rs` | Ingesta de documentos: deteccion de formato, extraccion de texto |
| `extractor.rs` | Extraccion de campos: pattern matching, scoring de confianza |
| `completer.rs` | Agente de completado: Q&A interactivo, validacion, finalizacion |
| `certifier.rs` | Certificacion de Blueprints: firma ECDSA, bridge a Fase 5 |
| `safety_gate_extended.rs` | Reglas de seguridad por dominio + compliance |
| `e2e_pipeline.rs` | Pipeline completo E2E de onboarding de nicho |

---

## Core Rust (PyO3 Native Extension)

El modulo `_zenic_native` expone **21 modulos Rust** de alto rendimiento a Python via `zenic-pybridge`:

| Modulo | Funcionalidad | Funciones/Clases |
|--------|--------------|-----------------|
| `crypto` | PBKDF2, Argon2id, comparacion tiempo constante | 3 funciones |
| `hash` | BLAKE3, xxHash64, Merkle root | 3 funciones |
| `db` | SQLCipher via rusqlite | 1 clase |
| `forensic` | Cadena Merkle, verificacion de integridad | 5 funciones |
| `rollback` | Rollback atomico cross-resource, snapshots | 5 funciones + 2 clases |
| `eventbus` | Dispatch de alta velocidad, wildcard matching, dedup | 5 funciones + 1 clase |
| `simulation` | Sort topologico DAG, dry-run, impacto | 4 funciones |
| `risk` | Radio de explosion, propagacion, camino critico | 5 funciones |
| `bus` | SharedMemoryBus, SharedState, RingBuffer | 3 clases |
| `safety_gate` | Validacion de seguridad determinista | 8 funciones + 3 clases |
| `license` | Licencias ECDSA, anti-tampering, hardware binding | 8 funciones + 3 clases |
| `niche` | Tipos de nicho compilados | 2 funciones + 7 clases |
| `catalog` | Catalogo de 24 nichos | 5 funciones |
| `template` | Generacion/validacion YAML de nichos | 6 funciones |
| `ingest` | Ingesta de documentos | 8 funciones + 3 clases |
| `extractor` | Extraccion de campos | 5 funciones + 2 clases |
| `completer` | Q&A interactivo de completado | 10 funciones + 4 clases |
| `certifier` | Certificacion de blueprints | 7 funciones + 7 clases |
| `safety_gate_extended` | Seguridad por dominio + compliance | 7 funciones + 3 clases |
| `e2e_pipeline` | Pipeline E2E de onboarding | 10 funciones + 3 clases |

**Total: 408+ tests | 100+ funciones PyO3 | 40+ clases PyO3**

---

## Capa Conversacional

Interaccion multi-turno unificada en `src/core/conversational/`:

| Modulo | Descripcion |
|--------|-------------|
| `conversation/` | Manager, State, Summarizer, Turn Tracker |
| `engine_parts/` | Response Generator, Formatter, Intent Classifier |
| `events/` | Event Bus + Event Types |
| `input/` | Parser, Enricher, Sanitizer |
| `knowledge/` | Knowledge Base |
| `memory/` + `memory_v2/` | Long-term, Short-term, Working Memory, Manager, Scorer |
| `routing/` | Router, Pipeline Selector, Fallback Chain, Intent Engine |
| `tools/` | Registry, Manager, Permissions, Executor |
| `config/` | Environment + Constants |
| `types/` | Memory, Events, Intent, Personality, Response, Tool Use, Session |
| `zenic_bridge.py` | Bridge al motor DAG Core |
| `session_manager.py` | Gestion de sesiones con estado estructurado |
| `personality_manager.py` | Personalidad y tono del asistente |
| `adapters/` | Telegram, Discord |

---

## Defense in Depth (6 Capas)

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
| Dispositivo objetivo | Android/Termux (CPU-only) |
| RAM | 4GB minimo (8GB+ recomendado) |
| GPU | No requerida |
| Modelo IA | Qwen3-0.6B Q4_K_M (378MB) |
| Motor de inferencia | llama-cpp-python |
| Tiempo por inferencia | ~2-5s (CPU) |
| RAM idle | ~50 MB |

---

## Instalacion

### Requisitos

- **Python**: 3.10+
- **Rust**: 1.85+ (para compilar la extension nativa)
- **RAM**: Minimo 4GB (8GB+ recomendado)
- **Disco**: ~500MB para modelo + dependencias
- **Opcional**: Z3 Solver, fastembed, Textual (TUI)

### Instalacion Rapida

```bash
# Clonar el repositorio
git clone git@github.com:yurislay9-ui/Zenic-Agents.git
cd Zenic-Agents

# Instalar dependencias core
pip install -r requirements.txt

# Compilar extension Rust nativa (requiere Rust 1.85+)
pip install maturin
cd zenic-v2/zenic-pybridge && maturin develop --release && cd ../..

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

### Compilar Workspace zenic-v2 (Rust puro)

```bash
cd zenic-v2
cargo build --release
cargo test --workspace
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
python src/entrypoints/main_headless.py --port 5000 --ram-limit 2048

# Servidor FastAPI (SaaS)
python src/entrypoints/main_headless.py --server fastapi --auth

# Modo daemon (background)
python src/entrypoints/main_headless.py --daemon
```

### Interfaz Textual (TUI)

```bash
pip install textual
python src/entrypoints/main.py
```

### Modo Asistente (Conversacional)

```bash
python src/entrypoints/main_conversational.py
```

---

## Estructura del Proyecto

```
Zenic-Agents/
├── pyproject.toml                   # Configuracion del proyecto + maturin
├── requirements.txt                 # Dependencias
├── Dockerfile                       # Docker build
├── docker-compose.yml               # Docker compose
├── buildozer.spec                   # Android/Termux build
├── docs/                            # Documentacion
│
├── zenic-v2/                        # Workspace Rust unificado (11 crates)
│   ├── Cargo.toml                   # Workspace config
│   ├── zenic-proto/                 # Tipos base, IDs, dominio
│   ├── zenic-graph/                 # Grafo DAG, subgrafos, supernodos
│   ├── zenic-runtime/               # Ejecutor, scheduler, contexto
│   ├── zenic-flow/                  # Motor de flujo, steps, retry
│   ├── zenic-policy/                # Roles, permisos, reglas
│   ├── zenic-safety/                # Veredictos, compliance
│   ├── zenic-core/                  # Orquestador, router, sesiones
│   ├── zenic-pybridge/              # Puente PyO3 (_zenic_native)
│   │   ├── Cargo.toml
│   │   ├── build.rs
│   │   └── src/                     # 21 modulos Rust
│   ├── zenic-ffi/                   # FFI bindings (stub)
│   ├── zenic-bench/                 # Benchmarks (stub)
│   └── zenic-tests/                 # Tests integracion (stub)
│
├── src/
│   ├── entrypoints/                 # Puntos de entrada
│   │   ├── main.py                  # Interfaz Textual (TUI)
│   │   ├── main_headless.py         # Servidor CLI
│   │   └── main_conversational.py   # Modo conversacional
│   │
│   ├── config/                      # Configuracion (YAML + loader)
│   │
│   ├── core/
│   │   ├── agents_v2/               # 42 Agentes SRP (9 capas)
│   │   │   ├── understanding/       # Capa 1: Intent, Entity, Target, Criticality
│   │   │   ├── memory/              # Capa 2: Memory, Relevance, Context
│   │   │   ├── business/            # Capa 3: Invoice, CRM, Inventory, Reports
│   │   │   ├── validation/          # Capa 5: Security, Syntax, Chain, Risk
│   │   │   ├── automation/          # Capa 6: Trigger, Action, Schedule
│   │   │   ├── reasoning/           # Capa 7: Problem, Step, Confidence
│   │   │   ├── verdict/             # Capa 8: Evidence, Consensus, VerdictEngine
│   │   │   ├── infrastructure/      # Capa 9: Runner, Health, Audit, CircuitBreaker
│   │   │   ├── resilience/          # Circuit breaker, retry, bulkhead
│   │   │   ├── schemas/             # Tipos compartidos
│   │   │   └── pipeline_orchestrator/ # Orquestador + niche onboarding
│   │   │
│   │   ├── agents/                  # Agentes V1 (legacy pipeline)
│   │   │   ├── intent_agent.py      # IntentAgent
│   │   │   ├── surgical_agent.py    # SurgicalAgent
│   │   │   ├── context_agent.py     # ContextAgent
│   │   │   ├── reasoning_agent.py   # ReasoningAgent
│   │   │   ├── business_logic_agent.py  # BusinessLogicAgent
│   │   │   ├── automation_agent.py  # AutomationAgent
│   │   │   ├── validation_agent.py  # ValidationAgent
│   │   │   └── criticality_agent.py # CriticalityAgent
│   │   │
│   │   ├── conversational/          # Capa conversacional multi-turno
│   │   ├── executors/               # 9 Executors (email, http, db, etc.)
│   │   ├── sna/                     # Sistema Nervioso Autonomo
│   │   ├── blueprints/              # Blueprints Certificados
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
│   │   ├── niche_rust/              # Python bridge a _zenic_native
│   │   ├── native/                  # Native module loader
│   │   └── ...                      # Otros sub-modulos
│   │
│   ├── server/                      # FastAPI HTTP server
│   │   ├── fastapi_app.py           # App principal
│   │   ├── fastapi_parts/           # Rutas modulares
│   │   ├── templates/               # Jinja2 (HTMX)
│   │   ├── static/                  # CSS + JS (Alpine.js, Chart.js)
│   │   └── security_middleware/     # Middleware de seguridad
│   │
│   └── templates/                   # DNA domain knowledge (YAML)
│       └── dna/                     # Glossary, logic modules, rules
│
├── tests/                           # 408+ tests
│   ├── unit/                        # Tests unitarios
│   ├── integration/                 # Tests de integracion
│   ├── e2e/                         # Tests end-to-end
│   └── phase_d/                     # Tests Phase D
│
├── deploy/                          # Docker, nginx, systemd, scripts
├── scripts/                         # Install + deploy scripts
└── .github/workflows/               # CI/CD (Rust+PyO3+Nuitka)
```

---

## Cambios v3.0.0 (Limpieza de Generador de Codigos)

Se eliminaron todos los modulos de generacion de codigo ya que Zenic es un **agente asistente**, no un generador de codigos:

| Eliminado | Razon |
|-----------|-------|
| `code_gen_parts/` (15 archivos) | CodeGenerator — genera codigo desde pipelines |
| `code_trans_parts/` (6 archivos) | CodeTransformer — refactoriza, corrige, optimiza |
| `app_gen_parts/` (7 archivos) | AppGenerator — genera apps completas |
| `template_parts/` (7 archivos) | TemplateEngine — motor Jinja2 de generacion |
| `fractal_parts/` (6 archivos) | FractalGenerator — genera apps multi-archivo |
| `schema_parts/` (7 archivos) | SchemaDesigner — genera modelos Python + SQL |
| `chain_valid_parts/` (5 archivos) | ChainValidator — valida cadenas de generacion |
| `agents/code_agent.py` + `code_agent_parts/` | CodeAgent V1 |
| `agents_v2/code_ops/` (6 archivos) | 6 agentes de operaciones de codigo (A17-A22) |
| `src/templates/apps/` (9 .j2) | Templates Jinja2 de apps |
| `src/templates/automations/` (5 .j2) | Templates Jinja2 de automatizaciones |
| `src/templates/blocks/` (22 .j2) | Templates Jinja2 de bloques de codigo |
| `docs/*.pdf` | Repositorio solo codigo |
| `agent-ctx/` | Artefactos de sesion anterior |

**Reorganizacion:**
- `native/` fusionado en `zenic-v2/zenic-pybridge/` (workspace Rust unificado)
- `main.py`, `main_conversational.py`, `main_headless.py` movidos a `src/entrypoints/`
- `.gitignore` actualizado con `.pytest_cache/`, `agent-ctx/`, `*.pdf`

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
# Ejecutar tests unitarios
pytest tests/unit/ -v

# Ejecutar tests de agentes por capas
pytest tests/unit/test_layer5_validation/ tests/unit/test_layer6_automation/ \
       tests/unit/test_layer7_reasoning/ tests/unit/test_layer8_verdict/ \
       tests/unit/test_layer9_infrastructure/ -v

# Ejecutar tests de integracion
pytest tests/integration/ -v

# Ejecutar tests E2E
pytest tests/e2e/ -v

# Tests Rust (workspace zenic-v2)
cd zenic-v2 && cargo test --workspace
```

---

## Tecnologias

| Componente | Tecnologia |
|-----------|-----------|
| Backend Python | Python 3.10+, FastAPI, Pydantic, asyncio |
| Core de rendimiento | Rust 1.85+, PyO3 0.22 |
| Base de datos | SQLCipher (Rust), SQLite WAL, PostgreSQL |
| Criptografia | BLAKE3, Argon2id, PBKDF2, ECDSA (Rust) |
| IA / LLM | Qwen3-0.6B, llama-cpp-python |
| Frontend | HTMX, Alpine.js, Chart.js, Jinja2 |
| Build Rust | maturin, Cargo |
| CI/CD | GitHub Actions, Nuitka |
| Deploy | Docker, nginx, systemd |
| Testing | pytest, pytest-asyncio, cargo test |

---

## Licencia

MIT License - ver [LICENSE](LICENSE) para detalles.

---

<div align="center">

**ZENIC-AGENTS** — 42 Agentes SRP | DAG 59 Nodos | 9 Executors | 24 Nichos Rust | SNA | Blueprints | Defense in Depth | Conversacional | PyO3

</div>
