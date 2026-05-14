<p align="center">
  <img src="https://img.shields.io/badge/version-3.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/Rust-PyO3-orange?style=for-the-badge" alt="Rust+PyO3">
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Platform-ARM64%20%7C%20x86__64-purple?style=for-the-badge" alt="Platform">
</p>

<h1 align="center">Zenic-Agents</h1>

<p align="center"><strong>Plataforma de Asistencia Empresarial Inteligente</strong></p>

<p align="center">
  IA como arbitro binario (SÍ/NO) | DAG Fractal de 121 nodos | Motor Rust de alto rendimiento | Defensa en 6 capas | 24 nichos industriales
</p>

---

## Tabla de Contenidos

- [Vision General](#vision-general)
- [6 Invariantes Arquitectonicos](#6-invariantes-arquitectonicos)
- [Arquitectura del Veredicto](#arquitectura-del-veredicto-4-capas)
- [Motor Rust (PyO3)](#motor-rust-pyo3)
- [Workspace Rust zenic-v2](#workspace-rust-zenic-v2)
- [24 Nichos Industriales](#24-nichos-industriales)
- [Safety Gate Inbypassable](#safety-gate-inbypassable)
- [Defensa en Profundidad](#defensa-en-profundidad-6-capas)
- [Sistema Nervioso Autonomo](#sistema-nervioso-autonomo-sna)
- [Ejecutores de Acciones](#19-ejecutores-de-acciones)
- [Sistema Distribuido](#sistema-distribuido)
- [Capa Conversacional](#capa-conversacional)
- [Billing y SaaS](#billing-y-saas)
- [Autopilot por Objetivos](#autopilot-por-objetivos)
- [Blueprints Certificados](#blueprints-certificados)
- [Servidor y API](#servidor-y-api)
- [Despliegue](#despliegue)
- [Instalacion Rapida](#instalacion-rapida)
- [Variables de Entorno](#variables-de-entorno)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Stack Tecnologico](#stack-tecnologico)
- [Comparativa](#comparativa-con-proyectos-similares)
- [Licencia](#licencia)

---

## Vision General

**Zenic-Agents** es una plataforma de asistencia empresarial inteligente con un principio radicalmente diferente a todo lo existente: **la IA NUNCA genera, solo arbitra SÍ o NO**. Toda tarea productiva es 100% deterministica. La IA (Qwen3-0.6B local, CPU-only) solo interviene como arbitro final cuando el pipeline deterministico no alcanza consenso.

Disenado para operar en dispositivos con recursos limitados: Android/Termux ARM64, CPU-only, 500MB-4GB RAM. Ningun competidor ofrece esta combinacion de seguridad, determinismo y eficiencia.

### Que hace diferente a Zenic-Agents

| Caracteristica | Zenic-Agents | Otros |
|---------------|-------------|-------|
| IA generativa | **Solo SÍ/NO (enjaulada)** | Genera codigo, texto, decisiones |
| Alucinaciones de IA | **Imposibles por diseno** | Riesgo constante |
| Funciona offline/CPU | **Si (Qwen3 local)** | Requiere API cloud |
| Android/Termux | **Disenado para eso** | No soportado |
| Motor Rust nativo | **16+ modulos PyO3** | Python puro |
| Safety Gate | **Inbypassable (doble capa)** | No existe |
| Anti-tampering | **6 capas con modo degradado** | No existe |

---

## 6 Invariantes Arquitectonicos

Estas son reglas que **no se pueden violar** bajo ninguna circunstancia:

1. **No LLM directo** — La IA nunca genera contenido. Solo emite veredictos binarios.
2. **Solo SÍ/NO** — La unica salida de la IA es un booleano. No hay gradaciones.
3. **Fallback deterministico** — Si la IA no responde, el sistema funciona con logica deterministica.
4. **Sin duplicacion** — Cada funcion tiene exactamente un responsable.
5. **Auditoria completa** — Toda accion queda registrada en Merkle Ledger inmutable.
6. **Veto de seguridad** — Si SafetyGate dice DENY, no existe override posible.

---

## Arquitectura del Veredicto (4 Capas)

El corazn de Zenic-Agents. Toda decision pasa por 4 capas secuenciales:

```
  Capa 1: DeterministicPipeline (7 tareas deterministicas)
      |
      v
  Capa 2: EvidenceCollector (evidencia a favor y en contra)
      |
      v
  Capa 3: ConsensusResolver (consenso multi-senal ponderado)
      |
      v
  Capa 4: VerdictEngine (arbitraje binario — IA solo si hay empate)
```

| Capa | Funcion | Usa IA? |
|------|---------|---------|
| **DeterministicPipeline** | Clasifica, extrae, genera, valida — 7 tareas sin IA | No |
| **EvidenceCollector** | Recoleccion de evidencia a favor y en contra | No |
| **ConsensusResolver** | Consenso multi-senal ponderado | No |
| **VerdictEngine** | Arbitraje SÍ/NO — solo interviene si hay empate | Solo SÍ/NO |

**Ningun otro proyecto hace esto.** En todos los demas, la IA genera respuestas que pueden ser incorrectas. Aqui la IA esta enjaulada: solo puede aprobar o rechazar, nunca crear.

---

## Motor Rust (PyO3)

Extension Python compilada con PyO3/maturin que expone operaciones de alto rendimiento implementadas en Rust. El modulo se importa como `_zenic_native`.

| Submodulo Rust | Funcion |
|----------------|---------|
| **crypto** | PBKDF2, Argon2id, comparacion en tiempo constante |
| **hash** | BLAKE3 (obligatorio), xxHash64, Merkle root |
| **db** | SQLCipher via rusqlite |
| **forensic** | Hash forense, verificacion de cadena Merkle, pruebas Merkle, verificacion batch |
| **rollback** | Snapshot/restauracion atomica de archivos |
| **eventbus** | Dispatch de eventos, wildcard matching, deduplicacion |
| **simulation** | Ordenamiento topologico DAG, deteccion de ciclos, simulacion dry-run |
| **risk** | Radio de explosion, propagacion de riesgos, camino critico |
| **bus** | SharedMemoryBus, RingBuffer, comunicacion inter-agente |
| **safety_gate** | Validacion de seguridad deterministica, rate limiting |
| **license** | Fingerprint de hardware, firma ECDSA, kill switch remoto |

Todos los modulos tienen fallback en Python (`src/core/native/_fallbacks.py`) para cuando la extension Rust no esta disponible.

---

## Workspace Rust zenic-v2

Workspace Rust puro con 10 crates, 7 completos con 408 tests:

| Crate | Funcion | Estado |
|-------|---------|--------|
| **zenic-proto** | Tipos compartidos, IDs, enums de dominio, serializacion bincode+zstd | Completo |
| **zenic-graph** | Primitivas de DAG fractal: NodeDescriptor, EdgeDescriptor, SuperNode, SubGraph, NodeCatalog | Completo |
| **zenic-flow** | Motor de workflows duraderos: Checkpoint/restore, SAGA compensation, RetryPolicy | Completo |
| **zenic-policy** | Motor de politicas: RBAC, reglas allow/deny, SafetyVeto inmutable, CriticalityGate | Completo |
| **zenic-safety** | Safety gate extendido: DomainSafetyGate (4 capas), ComplianceEngine, 35 reglas de dominio | Completo |
| **zenic-runtime** | Runtime: ExecutionContext, DagScheduler (topologico), MemoryManager, FractalLoader | Completo |
| **zenic-core** | Orquestador Rust: Orchestrator, Session, RequestRouter, DagStepExecutor | Completo |
| **zenic-ffi** | Interfaz FFI C para integracion con otros lenguajes | Completo |
| **zenic-pybridge** | Puente PyO3 con 16+ submodulos para Python | Completo |
| **zenic-bench** | Benchmarks de rendimiento | Stub |
| **zenic-tests** | Tests de integracion del workspace | Stub |

### DAG Fractal (3 niveles)

```
SuperNode (dominio + criticidad + load_policy)
  └── SubGraph (maximo 8 activos simultaneos)
       └── Node (hoja ejecutable)
```

Cada nodo tiene:
- **BusinessDomain** — 24 dominios de negocio
- **NodeCategory** — 17 categorias (Orchestrator, DataIngestion, Decision, Compliance, Verdict, etc.)
- **NodeCriticality** — 4 niveles (Critical, High, Medium, Low)
- **LoadPolicy** — Always, OnDemand, Cache, Lazy

---

## 24 Nichos Industriales

Los nichos son plantillas industriales compiladas estaticamente en Rust que definen reglas de seguridad, compliance regulatorio, campos de configuracion y comportamiento del pipeline para cada sector.

### 7 Categorias

| Categoria | Nichos | Compliance |
|-----------|--------|------------|
| **IA y Datos** | Automatización IA, Análisis de Datos, Operaciones ML, Servicios PLN | GDPR, SOC2 |
| **Tecnología Financiera** | Protocolos DeFi, Banca Digital, Tecnología Aseguradora, Tecnología Regulatoria | PCI-DSS, AML, KYC, SOX, Basel III |
| **Tecnología de la Salud** | Telemedicina, IA de Salud Mental, Genómica, Salud con Wearables | HIPAA, GDPR, FDA, GINA |
| **Tecnología Verde** | Seguimiento de Carbono, Red Eléctrica Inteligente, Economía Circular | GHG Protocol, NERC, IEC 61850 |
| **Tecnología Educativa** | Aprendizaje Adaptativo, Educación en RV, Microcredenciales | FERPA, COPPA |
| **Tecnología Inmobiliaria** | Edificios Inteligentes, Gemelos Digitales, Propiedad Fraccional | BREEAM, LEED, SEC, ISO 23247 |
| **Tecnología Jurídica** | Contratos Inteligentes, IA Jurídica, Automatización de Cumplimiento | SOX, eIDAS, ABA, ISO 27001 |

### 4 Niveles de Sensibilidad

| Nivel | Escalamiento de Veredicto |
|-------|---------------------------|
| **Low** | Sin escalamiento |
| **Medium** | Sin escalamiento |
| **High** | ALLOW → CONFIRM, CONFIRM → APPROVE |
| **Critical** | ALLOW → CONFIRM, CONFIRM → APPROVE, APPROVE → DENY |

### Pipeline de Onboarding (8 pasos)

```
1. SELECT_NICHE       → Buscar en catalogo + generar template
2. UPLOAD_DOCUMENTS   → Ingesta de documentos + extraccion de campos
3. GENERATE_QUESTIONS → Identificar campos faltantes
4. COLLECT_ANSWERS    → Q&A interactiva con validacion
5. VALIDATE_TEMPLATE  → Verificar completitud
6. SAFETY_CHECK       → Domain safety + compliance gate (inbypassable)
7. CERTIFY_BLUEPRINT  → Firma ECDSA + blueprint certificado
8. EXPORT             → Exportacion YAML + metadata
```

### 35 Reglas de Seguridad por Dominio (5 por categoria)

8 reglas tienen **DENY absoluto** — estas acciones no se pueden ejecutar bajo ninguna circunstancia:

| Regla | Dominio | Accion Bloqueada |
|-------|---------|-----------------|
| `fintech_unauthorized_transfer` | Tecnología Financiera | Transferencias no autorizadas |
| `fintech_compliance_bypass` | Tecnología Financiera | Bypass de compliance/KYC/AML |
| `healthtech_prescription_mod` | Tecnología de la Salud | Modificar recetas medicas |
| `edtech_grade_modify` | Tecnología Educativa | Modificar calificaciones |
| `edtech_content_filter` | Tecnología Educativa | Filtrar contenido educativo |
| `legaltech_document_delete` | Tecnología Jurídica | Borrar documentos legales |

---

## Safety Gate Inbypassable

Toda accion pasa por SafetyGate ANTES de ejecutarse. **Si devuelve DENY, no existe mecanismo de override.** Esto es arquitectonicamente garantizado, no convencionalmente.

### Doble capa Rust + Python

```
Accion del usuario
    |
    v
SafetyGate (Python) → categoriza: SAFE / MODERATE / DESTRUCTIVE / FINANCIAL / SYSTEM
    |
    v
DomainSafetyGate (Rust, 4 capas):
    Capa 1: 10 reglas genericas base
    Capa 2: 5 reglas de dominio (35 total)
    Capa 3: 8 estandares regulatorios (HIPAA, PCI-DSS, GDPR, SOX, AML, COPPA, ISO, SOC2)
    Capa 4: Escalamiento por sensibilidad (Critical → auto-deny)
    |
    v
DENY → BLOQUEADO (no hay override)
ALLOW / CONFIRM / APPROVE → ejecutar con restricciones
```

**Invariantes del Safety Gate:**
- Las reglas de dominio SOLO PUEDEN ESCALAR veredictos, **nunca degradar**
- Si la base devuelve DENY, el domain gate **no puede** sobreescribir
- Violaciones criticas de compliance → **DENY automatico**
- Toda la logica es **deterministica** — sin IA, sin aleatoriedad

---

## Defensa en Profundidad (6 Capas)

| Capa | Componente | Funcion |
|------|-----------|---------|
| **1** | Anti-Tampering | Anti-debug (ptrace), deteccion de timing anomaly, verificacion de integridad de codigo, monitoreo continuo en background |
| **2** | Binary Hardening | Nuitka compilation, Rust FFI, code signing |
| **3** | Encryption | SQLCipher + Fernet + PBKDF2 + hardware binding |
| **4** | Integrity | Hash chains, cross-verification, monitoreo de archivos criticos |
| **5** | Licensing | ECDSA signing, kill switch remoto, heartbeat |
| **6** | Server Secrets | Verificacion remota, grace period |

Si detecta tampering → **modo degradado** (paralisis selectiva, solo lectura). El DefenseManager orquesta las 6 capas con scoring 0-100 y escalado automatico.

---

## Sistema Nervioso Autonomo (SNA)

Monitoreo proactivo **sin que el usuario pida nada**. 13 monitores en 3 pesos:

| Peso | Monitores |
|------|----------|
| **Lightweight** | LowStock, OverdueInvoice, TomorrowAppointment, DiskSpace, SystemHealth |
| **Medium** | SalesTrend, CRMConversion, ResponseTime, ErrorRate |
| **Heavy** | DemandProjection, MultiSourceAnalysis, CapacityPlanning |

Incluye: alarmas Android/Termux wake-up, deduplicacion de alertas, bypass reflejo para lo time-critical, y persistencia SQLite/SQLCipher.

---

## 19 Ejecutores de Acciones

Todos pasan por SafetyGate + AuditLogger antes de ejecutarse:

| Ejecutor | Funcion |
|----------|---------|
| DatabaseExecutor | CRUD en SQLCipher/SQLite |
| EmailExecutor | Envio de emails con templates y rate limiting |
| FileExecutor | Operaciones de archivos (read/write/delete/move) |
| HTTPExecutor | Requests HTTP/HTTPS |
| WebhookExecutor | Disparo de webhooks |
| ScheduleExecutor | Programacion de tareas (APScheduler) |
| NotificationExecutor | Notificaciones multi-canal con rate limiting |
| DiscordExecutor | Integracion con Discord |
| TransformExecutor | Transformaciones de datos |
| DryRunExecutor | Simulacion sin efectos reales |
| SimulationEngine | Simulacion de impacto DAG (dry-run) |
| PolicyEngine | Motor de politicas para ejecutores |
| ImpactPreview | Vista previa de impacto antes de ejecutar |
| CoordinatedRollback | Rollback atomico cross-recurso |
| AuditLogger | Auditoria de todas las acciones (Merkle + persistencia) |
| BlueprintSchema | Esquema para ejecutores de blueprints |
| DispatchAction | Despacho central de acciones |
| DiffPreview | Vista previa de diffs |
| DBJournal | Journaling de operaciones DB |

---

## Sistema Distribuido

Transforma patrones de un solo proceso en componentes multi-nodo respaldados por PostgreSQL:

| Componente | Funcion |
|-----------|---------|
| PgBackend | Backend PostgreSQL (produccion) |
| MemoryBackend | Backend en-proceso (dev/testing) |
| DistributedTaskQueue | Cola de tareas persistente con prioridad + leasing |
| DistributedWorker | Worker con heartbeats, auto-discovery, work-stealing |
| DistributedSagaCoordinator | SAGA cross-proceso con estado persistido |
| DistributedCircuitBreaker | Circuit breaker con estado compartido |
| LeaderElection | Eleccion de lider (PostgreSQL advisory locks) |
| DistributedLockManager | Locking distribuido cross-nodo |
| ClusterTopology | Registro de nodos, heartbeats, gestion de topologia |

---

## Capa Conversacional

Motor de conversacion multi-turno con:

- **Sesiones** multi-turno con estado
- **Adaptadores de canal**: Telegram, Discord
- **Memoria**: Working/Episodic/Long-term (v1 + v2)
- **Personalidad** configurable
- **Herramientas** con permisos granulares
- **Confirm Manager** para acciones sensibles
- **LLM Translator/Drafter** para interaccion en lenguaje natural

---

## Billing y SaaS

Subsistema completo de facturacion SaaS:

| Componente | Funcion |
|-----------|---------|
| BillingService | Fachada unificada (singleton) |
| StripeClient | Integracion HTTP real con Stripe API |
| SubscriptionManager | Lifecycle de suscripciones, uso, control de acceso |
| TrialManager | Trials con inicio, expiracion, extension, recordatorios |
| WebhookHandler | Procesamiento de webhooks de Stripe |
| Planes | Free / Pro / Enterprise |

---

## Autopilot por Objetivos

Automatizacion autonoma orientada a KPIs de negocio:

```
Objetivo → Descomposicion → Ejecucion → Medicion → Ajuste
```

- **Objective**: Objetivo de negocio con targets medibles
- **KPITracker**: Medicion y analisis de tendencias
- **AutopilotPlanner**: Descomposicion en pasos accionables
- **ClosedLoopFeedback**: Medicion de resultados y ajuste de estrategia
- **AutonomyConfig**: Niveles de autonomia (aprobacion humana → auto-ejecucion)

---

## Blueprints Certificados

Sistema de plantillas YAML → Blueprints certificados con firma ECDSA:

- **BlueprintLoaderV2**: Carga desde YAML/JSON/dict
- **NicheConverter**: Conversion Niche YAML → CertifiedBlueprint
- **BlueprintComposer**: Composicion de multiples Blueprints
- **BlueprintValidatorV2**: Validacion de schema + compatibilidad
- **BlueprintCertifier**: Firma ECDSA + verificacion
- **OnboardingEngine**: Flujo de setup guiado
- **BlueprintSDK**: API para partners + revenue share
- **PartnerRegistry**: Registro de partners

## Yamil — Agente Creador de Plantillas

**Yamil** es el agente unificado de creacion de plantillas que orquesta el flujo completo desde la seleccion de nicho hasta la certificacion del Blueprint. Integra y simplifica los componentes que antes estaban fragmentados (NicheBridge, NicheOnboardingPipeline, NicheConverter, OnboardingEngine, BlueprintCertifier).

### Flujo de Yamil

```
1. Seleccionar nicho         → list_niches() / search_niches()
2. Crear plantilla            → create_template("telemedicine")
3. Llenar campos              → fill_field() / fill_fields_batch()
4. Validar completitud        → validate()
5. Safety check (inbypassable)→ safety_check()
6. Certificar ECDSA           → certify()
7. Exportar YAML              → export_yaml()
```

### API Principal

```python
from src.core.agents.yamil import YamilAgent

yamil = YamilAgent()

# Explorar nichos
niches = yamil.list_niches()          # 24 nichos
categories = yamil.list_categories()   # 7 categorias
results = yamil.search_niches("health") # Busqueda por texto

# Crear plantilla
result = yamil.create_template("telemedicine")
session_id = result.session_id

# Llenar campos
yamil.fill_field(session_id, "business_identity", "business_name", "Mi Clinica")
yamil.fill_fields_batch(session_id, {
    "business_type": "Healthcare",
    "tax_id": "123456789",
    "country": "CU",
    "admin_email": "admin@clinic.com",
})

# Completar pipeline
yamil.validate(session_id)
yamil.safety_check(session_id)
yamil.certify(session_id, private_key="...")
yaml_output = yamil.export_yaml(session_id)

# O ejecutar todo de una vez
result = yamil.run_full(
    niche_id="telemedicine",
    answers={"business_name": "Mi Clinica", ...},
    private_key="...",
)
```

### Caracteristicas

| Caracteristica | Detalle |
|---------------|---------|
| **Hereda de BaseAgent** | Implementa build_prompt, parse_response, fallback |
| **Fallback deterministico** | Funciona sin Rust extension (24 nichos hardcodeados) |
| **Sesiones resumables** | Cada paso puede reintentarse independientemente |
| **Audit log** | Toda accion queda registrada con timestamp |
| **Safety Gate inbypassable** | Si DENY, el pipeline se detiene |
| **57 tests** | Cobertura completa de catalogo, template, validacion, safety, certificacion |

---

## Servidor y API

Servidor **OpenAI-compatible** en puerto 5000 con FastAPI:

### Endpoints principales

| Endpoint | Funcion |
|----------|---------|
| `POST /v1/chat/completions` | Chat con SSE streaming (compatible con Cline/Aide/OpenCode) |
| `POST /v1/generate/*` | Generacion deterministica |
| `POST /v1/think` | Motor de pensamiento |
| `POST /v1/reason` | Razonamiento multi-paso |
| `POST /v1/chain/*` | Cadenas de agentes |
| `POST /v1/actions/*` | Ejecutores de acciones |
| `GET /health` | Health check |
| `GET /v1/models` | Modelos disponibles |

### UI Web

Dashboard web completo con HTMX/Alpine/Chart.js: CRM, billing, audit, SNA, inventory, onboarding, settings, defense, license, channels, ROI, modules.

### Entrypoints

| Modo | Comando |
|------|---------|
| **TUI** | `python -m src.entrypoints.main` |
| **Conversacional** | `python -m src.entrypoints.main_conversational` |
| **Headless CLI** | `python -m src.entrypoints.main_headless` |
| **Servidor HTTP** | `uvicorn src.server.fastapi_app:create_app_from_env --factory` |

---

## Despliegue

### Docker (recomendado)

```bash
# Build
docker build -t zenic-agents:latest .
docker build --target production -t zenic-agents:prod .

# Run
docker-compose up -d
```

### VPS manual

```bash
# Usando el script de despliegue
bash deploy/scripts/deploy-vps.sh

# O manualmente
pip install -r requirements.txt
cd zenic-v2/zenic-pybridge && maturin develop --release && cd ../..
uvicorn src.server.fastapi_app:create_app_from_env --host 0.0.0.0 --port 5000 --factory
```

### Termux / Android

```bash
pkg install python rust
pip install -r requirements.txt
cd zenic-v2/zenic-pybridge && maturin develop --release && cd ../..
python main.py
```

---

## Instalacion Rapida

```bash
# 1. Clonar
git clone https://github.com/yurislay9-ui/Zenic-Agents.git
cd Zenic-Agents

# 2. Instalar dependencias Python
pip install -r requirements.txt

# 3. Compilar extension Rust (opcional pero recomendado)
cd zenic-v2/zenic-pybridge
maturin develop --release
cd ../..

# 4. Iniciar servidor
uvicorn src.server.fastapi_app:create_app_from_env --host 0.0.0.0 --port 5000 --factory
```

### Instalacion con extras

```bash
pip install -e ".[all]"        # Todo (Z3, embeddings, Stripe, LLM)
pip install -e ".[z3]"         # Solver Z3 SMT
pip install -e ".[tui]"        # TUI con Textual
pip install -e ".[stripe]"     # Integracion Stripe
pip install -e ".[llm]"        # Soporte LLM local (llama.cpp)
pip install -e ".[observability]" # OpenTelemetry + Prometheus
```

---

## Variables de Entorno

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `ZENIC_ENV` | `development` | Entorno: development / production |
| `ZENIC_SERVER_MODE` | `fastapi` | Modo: fastapi / http |
| `ZENIC_PORT` | `5000` | Puerto del servidor |
| `ZENIC_AUTH_ENABLED` | `false` | Habilitar autenticacion |
| `ZENIC_DATA_DIR` | `~/.zenic-agents/data` | Directorio de datos |
| `ZENIC_DB_URL` | `sqlite+aiosqlite:///zenic.db` | URL de base de datos |
| `ZENIC_USE_UNIFIED_DAG` | `0` | Activar agentes v2 (experimental) |
| `ZENIC_LICENSE_KEY` | — | Clave de licencia |

---

## Estructura del Proyecto

```
Zenic-Agents/
├── main.py                    # Entrypoint TUI
├── main_conversational.py     # Entrypoint conversacional
├── main_headless.py           # Entrypoint headless CLI
├── pyproject.toml             # Configuracion del proyecto
├── requirements.txt           # Dependencias Python
├── Dockerfile                 # Multi-stage: Rust → Python → Production
├── deploy/                    # Despliegue (nginx, systemd, scripts, SQL)
│
├── src/
│   ├── core/
│   │   ├── agents/            # Agentes v1 (10 agentes especializados)
│   │   ├── agents_v2/         # Agentes v2 (9 capas, ~30 agentes)
│   │   ├── verdict_parts/     # Arquitectura de veredicto (4 capas)
│   │   ├── mini_ai_parts/     # Motor de IA mini (Qwen3, solo SÍ/NO)
│   │   ├── executors/         # 19 ejecutores de acciones + SafetyGate
│   │   ├── defense/           # Defensa en 6 capas
│   │   ├── license/           # Licenciamiento criptografico ECDSA
│   │   ├── billing/           # SaaS billing + Stripe
│   │   ├── distributed/       # Sistema distribuido (PgBackend, SAGA, etc.)
│   │   ├── conversational/    # Capa conversacional multi-turno
│   │   ├── autopilot/         # Autopilot por objetivos
│   │   ├── blueprints/        # Blueprints certificados ECDSA
│   │   ├── chaos/             # Chaos engineering
│   │   ├── knowledge/         # Grafo de conocimiento
│   │   ├── learning/          # Motor de aprendizaje
│   │   ├── plugins/           # Sistema de plugins
│   │   ├── patterns/          # 30+ patrones de diseno
│   │   ├── observability/     # Tracing, metricas, audit, forense
│   │   ├── sna/               # Sistema Nervioso Autonomo
│   │   ├── native/            # Puente Rust (_zenic_native) + fallbacks
│   │   ├── niche_rust/        # Bridge de nichos Rust → Python
│   │   ├── shared/            # Infraestructura compartida (DB, bus, Z3, etc.)
│   │   └── ...                # +20 modulos mas
│   │
│   ├── server/                # FastAPI + HTTP server + UI web
│   │   ├── fastapi_parts/     # App factory, rutas, middleware
│   │   ├── htmx_routes/       # Rutas HTMX para UI web
│   │   ├── templates/         # Jinja2 templates (dashboard, CRM, etc.)
│   │   └── static/            # CSS, JS (Alpine, Chart.js, HTMX)
│   │
│   └── templates/
│       └── dna/               # Templates DNA (reglas, modulos, glosario)
│
├── native/                    # Extension Rust PyO3 (modulos nativos)
│   ├── Cargo.toml
│   └── src/                   # crypto, hash, db, forensic, rollback, etc.
│
├── zenic-v2/                  # Workspace Rust puro (10 crates)
│   ├── zenic-proto/           # Tipos compartidos, IDs, serializacion
│   ├── zenic-graph/           # DAG fractal (nodos, aristas, SuperNodes)
│   ├── zenic-flow/            # Workflows duraderos, SAGA, checkpoint
│   ├── zenic-policy/          # RBAC, SafetyVeto, CriticalityGate
│   ├── zenic-safety/          # DomainSafetyGate, ComplianceEngine
│   ├── zenic-runtime/         # Scheduler topologico, MemoryManager
│   ├── zenic-core/            # Orquestador Rust
│   ├── zenic-ffi/             # FFI C interface
│   ├── zenic-pybridge/        # Puente PyO3 (16+ submodulos)
│   ├── zenic-bench/           # Benchmarks
│   └── zenic-tests/           # Tests de integracion
│
├── tests/
│   ├── unit/                  # Tests unitarios por capa
│   └── e2e/                   # Tests end-to-end
│
└── agent-ctx/                 # Contexto de agentes (documentacion)
```

---

## Stack Tecnologico

| Capa | Tecnologia |
|------|-----------|
| **Backend** | Python 3.10+, FastAPI, Uvicorn, Gunicorn |
| **Motor nativo** | Rust (PyO3/maturin), BLAKE3, SQLCipher, Argon2id |
| **IA** | Qwen3-0.6B (CPU-only, local), OpenAI API compatible |
| **Base de datos** | SQLite/SQLCipher (dev), PostgreSQL (produccion) |
| **Billing** | Stripe API (HTTP real) |
| **Observabilidad** | OpenTelemetry, Prometheus, Jaeger |
| **Frontend** | HTMX, Alpine.js, Chart.js, Jinja2 |
| **Solver** | Z3 SMT, MCTS (Monte Carlo Tree Search) |
| **Seguridad** | ECDSA, PBKDF2, Fernet, Anti-tampering, Kill switch |
| **Despliegue** | Docker multi-stage, Nginx, Systemd |
| **Plataformas** | x86_64, ARM64 (Android/Termux) |

---

## Comparativa con Proyectos Similares

| Caracteristica | **Zenic-Agents** | LangChain | AutoGPT | CrewAI | Semantic Kernel |
|---------------|-----------------|-----------|---------|--------|----------------|
| IA solo SÍ/NO | **Si** | No | No | No | No |
| Fallback deterministico 100% | **Si** | No | No | No | Parcial |
| Offline / CPU-only | **Si** | No | No | No | No |
| Android/Termux | **Si** | No | No | No | No |
| Motor Rust nativo | **16+ modulos** | No | No | No | No |
| Safety Gate inbypassable | **Doble capa** | No | No | No | No |
| Anti-tampering 6 capas | **Si** | No | No | No | No |
| 24 nichos industriales | **Si** | No | No | No | No |
| Compliance (HIPAA/GDPR/PCI) | **8 estandares** | No | No | No | No |
| Billing/Stripe | **Integrado** | No | No | No | No |
| Chaos Engineering | **Integrado** | No | No | No | No |
| SAGA distribuida | **Si** | No | No | No | No |
| API OpenAI-compatible | **Drop-in** | Framework | No | No | No |
| 500MB RAM minimo | **Disenado para eso** | Pesado | Muy pesado | Pesado | Pesado |
| Madurez ecosistema | Nuevo | Muy maduro | Popular | Creciendo | Corporativo |

---

## Licencia

Propietaria. Todos los derechos reservados. El uso requiere licencia valida firmada con ECDSA. Consulte los terminos de licencia antes de usar este software.

---

<p align="center">
  <strong>Zenic-Agents</strong> — IA enjaulada. Seguridad por diseno. Determinismo garantizado.
</p>
