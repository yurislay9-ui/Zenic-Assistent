# Zenic-Agents — Plan de Implementacion por Fases

> Documento de referencia que contiene el estado actual del proyecto, los gaps identificados,
> y el plan detallado de implementacion por fases (0-7).

---

## Estado Actual vs Estado Final

| Componente Whitepaper | Equivalente Actual | Estado |
|---|---|---|
| DAG Core 59 nodos | `src/core/dag_parts/` (unified_orchestrator + definition) | COMPLETO |
| VerdictEngine (AI binario) | `src/core/agents_v2/verdict/` + `verdict_engine_module.py` | COMPLETO |
| Safety Gate (parcial) | `agents_v2/validation/SecurityScanner` + veto de seguridad | COMPLETO |
| 9 Executors | `src/core/executors/` (9 tipos: email, http, db, file, etc.) | COMPLETO |
| Session Manager | `src/core/auth_parts/` + JWT/RBAC | PARCIAL - API-only, no conversacional |
| SharedMemoryBus | `src/core/shared/shared_memory_bus.py` | COMPLETO |
| FastConnectionPool | `src/core/shared/fast_connection_pool.py` | COMPLETO |
| Multi-tenancy | `src/core/tenant/` + planes Free/Pro/Enterprise | PARCIAL - Multi-tenant, no multi-rol |
| Observabilidad | `src/core/observability/` + Prometheus | COMPLETO |
| Distribucion (SAGA) | `src/core/distributed/saga_coordinator.py` | COMPLETO |
| Patrones de resiliencia | `src/core/patterns/` (18 modulos) | COMPLETO |
| API OpenAI-compatible | `src/server/fastapi_app.py` + `/v1/chat/completions` | COMPLETO |
| Docker/Deploy | `Dockerfile` + `docker-compose.yml` | COMPLETO |
| Capa Conversacional | `src/core/conversational/` | COMPLETO |
| SNA | `src/core/sna/` (scheduler, monitores, thresholds) | COMPLETO |
| Blueprints Certificados | `src/core/blueprints/` (schema, loader, onboarding, sdk) | COMPLETO |
| Multi-Rol + Aprobacion | `src/core/approval/` + `src/core/auth_parts/` | COMPLETO |
| Defense in Depth | `src/core/defense/` (6 capas) | COMPLETO |
| Licenciamiento ECDSA | `src/core/license/` (signer, hardware binding) | COMPLETO |
| Modo Degradado | `src/core/degraded_mode/` | COMPLETO |
| Billing (Stripe) | `src/core/billing/` | COMPLETO |
| Frontend HTMX+Alpine.js | `src/server/templates/` + `src/server/static/` | COMPLETO |
| CI/CD GitHub Actions | `.github/workflows/build.yml` | COMPLETO |

---

## Gaps Pendientes (7 Cambios Estructurales + Rust)

| # | Cambio | Gap Actual | Prioridad |
|---|---|---|---|
| **C1** | **Core en Rust (PyO3)** | Todo esta en Python | CRITICO |
| **C2** | **Capa Conversacional** | Solo API/HTTP, sin multi-turno | RESUELTO - Implementado en Fase 2 |
| **C3** | **Sistema Nervioso Autonomo (SNA)** | No existia monitoreo proactivo | RESUELTO - Implementado en Fase 4 |
| **C4** | **Blueprints certificados** | Templates YAML fijos | RESUELTO - Implementado en Fase 5 |
| **C5** | **De Multi-Tenant a Multi-Rol Colaborativo** | Tenant aislado, sin roles | RESUELTO - Implementado en Fase 6 |
| **C6** | **Data-Aware (SQLCipher)** | SQLite sin cifrado | PARCIAL - Estructura lista, SQLCipher pendiente |
| **C7** | **Defense in Depth (6 capas)** | Sin anti-tampering | RESUELTO - Implementado en Fase 6 |

---

## FASE 0 — Fundacion Rust + PyO3 (2-3 semanas) — PENDIENTE

**Objetivo**: Crear el puente Rust<->Python y mover los componentes criticos.

### Tareas:
- **0.1** Inicializar workspace Rust (cargo) dentro del repo
  - Crear `/rust/zenic-core/` con Cargo.toml + pyo3 dependency
  - Configurar maturin/PyO3 para build integration

- **0.2** Implementar SharedMemoryBus en Rust
  - Port de RingBuffer + Mailbox + SharedState a Rust
  - PyO3 bindings para que Python acceda via FFI
  - Test: performance debe ser >= Python actual

- **0.3** Implementar Crypto Layer en Rust
  - PBKDF2-SHA256 para derivacion de claves
  - Hardware fingerprint (CPU+disk+memory ID)
  - SQLCipher bindings (via rusqlite + sqlcipher)

- **0.4** Migrar DAG Definition a Rust structs
  - Port de DAGNode, PIPELINE_DAG (59 nodos) a Rust
  - DAG execution engine en Rust (async via tokio)
  - PyO3 expose: DAGOrchestrator.execute() callable desde Python

**Entregable**: `cargo build` + `maturin develop` funciona, Python puede llamar Rust DAG

**Archivos afectados**:
- `NUEVO`: `/rust/zenic-core/src/lib.rs`, `dag.rs`, `crypto.rs`, `bus.rs`
- `NUEVO`: `/rust/zenic-core/Cargo.toml` (pyo3, tokio, rusqlite)
- `MODIFICAR`: `pyproject.toml` (anadir maturin build)
- `MODIFICAR`: `src/core/dag_orchestrator.py` (delegate a Rust cuando disponible)

---

## FASE 1 — Core Rust: Safety Gate + DAG Core (3-4 semanas) — PARCIAL

**Objetivo**: Safety Gate en Rust + DAG funcional desde Rust.

### Tareas:
- **1.1** Safety Gate en Rust
  - Reglas deterministas inquebrantables:
    * Acciones destructivas (DELETE masivo) -> requiere confirmacion
    * Acciones financieras (facturas, pagos) -> requiere aprobacion
    * Acciones multi-registro -> rate limiting + validacion
  - PyO3 binding: SafetyGate::validate(action) -> Verdict
  - INTEGRAR en el pipeline ANTES de executors

- **1.2** DAG Core 59 nodos en Rust
  - Port de las 6 fases: Understand, Context, Routing, Validate, Verdict, Sandbox
  - Cada nodo como Rust struct con execute() method
  - Paralelizacion con tokio::spawn para grupos paralelos
  - Routing condicional por path (code/biz/auto/reason/solver)

- **1.3** MVP de linea de comando
  - CLI que invoca DAG Core via PyO3
  - Test: flujo end-to-end simple (ej: "crear factura para cliente X")
  - Benchmark: Rust DAG vs Python DAG (target: 5-10x mas rapido)

**Entregable**: `zenic-cli process "crear factura"` funciona usando Rust DAG

**Archivos afectados**:
- `NUEVO`: `/rust/zenic-core/src/safety_gate.rs`
- `NUEVO`: `/rust/zenic-core/src/dag/` (nodos, fases, routing)
- `NUEVO`: `/rust/zenic-core/src/cli.rs`
- `MODIFICAR`: `src/core/executors/` -> recibir validacion de Safety Gate

---

## FASE 2 — Capa Conversacional (2-3 semanas) — COMPLETA

**Objetivo**: De API-only a conversacional multi-turno.

### Implementado en `src/core/conversational/`:
- **Session Manager** con estado estructurado (`session_manager.py`)
- **LLM Translator** (entrada) — Convierte lenguaje natural -> peticion estructurada DAG
- **LLM Drafter** (salida) — Convierte respuesta DAG -> lenguaje natural
- **Confirm Manager** — Flujo de confirmacion para acciones criticas
- **Conversation Manager** — State, Summarizer, Turn Tracker
- **Routing** — Router, Pipeline Selector, Fallback Chain, Intent Engine
- **Memory** — Long-term, Short-term, Working Memory, Manager, Scorer
- **Tools** — Registry, Manager, Permissions, Executor
- **Events** — Event Bus + Event Types
- **Input** — Parser, Enricher, Sanitizer
- **Knowledge Base** — Modulo de conocimiento
- **Personality Manager** — Personalidad y tono del asistente
- **Zenic Bridge** — Conexion al motor DAG Core
- **Adapters** — Telegram + Discord (estructura preparada)

---

## FASE 3 — 9 Executors Directos (2-3 semanas) — COMPLETA

**Objetivo**: Executors integrados con Safety Gate y Blueprints.

### Implementado en `src/core/executors/`:
- **9 tipos**: email, http, db, file, notification, schedule, transform, webhook, base
- **Integracion Safety Gate**: validacion previa antes de ejecucion
- **Parametrizacion Blueprint**: schema de datos por Blueprint
- **Auditoria por accion**: log estructurado de cada ejecucion
- **Email Executor**: SMTP con templates, attachments, rate limiting
- **Database Executor**: CRUD validado con schema por Blueprint
- **Notification Executor**: Multi-canal (Telegram/Discord/Email)
- **Integracion DAG -> Executor pipeline**: DISPATCH_ACTION -> selecciona executor

---

## FASE 4 — Sistema Nervioso Autonomo (2-3 semanas) — COMPLETA

**Objetivo**: Monitoreo proactivo + notificaciones sin solicitud del usuario.

### Implementado en `src/core/sna/`:
- **Scheduler de monitores** (`scheduler.py`): Cola de prioridad con intervalos configurables
- **Monitores clasificados** (`monitores/`):
  * LIVIANOS: stock bajo, factura vencida, cita manana
  * MEDIANOS: tendencia de ventas, ratio de conversion CRM
  * PESADOS: analisis multi-fuente, proyecciones de demanda
- **Motor de umbrales** (`thresholds.py`): Configurables por Blueprint + usuario
- **Notificacion proactiva**: SNA -> DAG -> valida -> notifica
- **SNA -> DAG integration**: Notificaciones pasan por el mismo DAG

---

## FASE 5 — Blueprints Certificados (3-4 semanas) — COMPLETA

**Objetivo**: De YAML templates fijos a Blueprints modulares componibles.

### Implementado en `src/core/blueprints/`:
- **Blueprint Schema** (`schema.py`): Metadata + schema DB + reglas + monitores + acciones
- **Blueprint Loader & Composer** (`loader.py`): Carga + composicion + resolucion conflictos
- **Migracion templates**: niches/ -> Blueprints certificados con firma ECDSA
- **Sistema de Onboarding** (`onboarding.py`): Seleccion + procesamiento + auto-config
- **Blueprint SDK** (`sdk.py`): API para partners crear Blueprints custom

---

## FASE 6 — Multi-Rol + Seguridad Completa (3-4 semanas) — COMPLETA

**Objetivo**: Roles granulares + cadenas de aprobacion + Defense in Depth + Licenciamiento.

### Implementado:
- **Multi-Rol Colaborativo** (`src/core/auth_parts/` + `src/core/approval/`):
  * Roles admin/gerente/operador/viewer con permisos granulares
  * Cadenas de aprobacion para acciones criticas
  * Workflows configurables con notificaciones en cada paso

- **Defense in Depth (6 capas)** (`src/core/defense/`):
  * Capa 1: mlock + anti-debug + anti-ptrace (estructura Rust)
  * Capa 2: Nuitka compilation + Rust binary
  * Capa 3: SQLCipher + Fernet + PBKDF2
  * Capa 4: Hash chain integrity + cross-verification
  * Capa 5: Licenciamiento ECDSA
  * Capa 6: Server-side secrets

- **Licenciamiento Criptografico** (`src/core/license/`):
  * ECDSA signing + verification
  * Hardware binding (fingerprint)
  * Kill switch remoto

- **Modo Degradado / Paralysis** (`src/core/degraded_mode/`):
  * Licencia vencida -> Modo Degradado (solo lectura)
  * Tampering detectado -> Modo Paralysis (3 niveles)
  * Actualizacion pendiente -> Modo Restrictivo

---

## FASE 7 — Frontend Web + Cierre Beta (4 semanas) — COMPLETA

**Objetivo**: Panel de control HTMX + cierre de beta.

### Implementado:
- **Frontend HTMX + Alpine.js** (`src/server/templates/` + `src/server/static/`):
  * Modulos: Onboarding, Canales, Inventario, Dashboard, CRM, Facturacion, SNA, Audit

- **Dashboard Ejecutivo**: Metricas con Chart.js, auto-refresh via HTMX polling
- **Configuracion SNA visual**: Monitores activos, umbrales con sliders
- **Audit Trail visual**: Filtros, historial DAG, exportacion CSV/JSON
- **CI/CD GitHub Actions** (`.github/workflows/build.yml`): Rust+PyO3+Nuitka build
- **Trial + Billing** (`src/core/billing/`): Stripe integration, 14-day trial, auto-degradacion

---

## Resumen de Decision Arquitectonica

| Dimension | Estado Actual | Estado Final |
|---|---|---|
| **Lenguaje** | 100% Python | Rust Core + Python Shell (Rust pendiente) |
| **IA** | Qwen3-0.6B veredicto binario | Qwen2.5-1.5B/3B/7B (traduccion + redaccion) |
| **Interaccion** | API HTTP + Conversacional | Conversacional (Telegram/Discord/Web) |
| **Ejecucion** | 9 Executors predefinidos | 9 Executors con Safety Gate |
| **Proactividad** | SNA completo | SNA con scheduler + monitores + alertas |
| **Templates** | Blueprints certificados | Blueprints componibles con ECDSA |
| **Usuarios** | Multi-rol colaborativo | Multi-rol con cadenas de aprobacion |
| **Base datos** | SQLite | SQLCipher cifrado (pendiente integracion) |
| **Seguridad** | Defense in Depth 6 capas | 6 capas con Rust (pendiente compilacion) |
| **Licenciamiento** | ECDSA + hardware binding | ECDSA con Rust (pendiente compilacion) |
| **Deployment** | Docker + Termux | Docker + Termux + Nuitka binary |

---

## Estrategia de Migracion (Principio: Impacto Minimo)

1. **Compatibilidad hacia atras**: Cada capa Rust se envuelve en fallback Python. Si Rust falla -> Python toma el relevo.
2. **Feature flags**: `ZENIC_USE_RUST_DAG=1`, `ZENIC_USE_SNA=1`, etc. Para activar gradualmente.
3. **Tests primero**: Cada modulo Rust se testea contra el comportamiento del modulo Python equivalente.
4. **Incremental**: No reescribir todo de golpe. Port componente por componente, verificando en cada paso.

---

## Pendientes Criticos

1. **Rust FFI (Fase 0-1)**: Compilar core Rust con PyO3
2. **SQLCipher**: Integrar cifrado real de base de datos
3. **55 archivos exceden 400 lineas**: Refactorizar para cumplir la regla
4. **Executors no accesibles desde stdlib server**: Conectar rutas
5. **Feature flags**: Cablear flags reales
6. **E2E Tests**: Tests end-to-end completos
