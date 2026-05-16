<p align="center">
  <img src="https://img.shields.io/badge/version-3.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/Rust-PyO3_12_Crates-orange?style=for-the-badge" alt="Rust+PyO3">
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/TypeScript-Next.js_16-blue?style=for-the-badge" alt="TypeScript">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Platform-ARM64%20%7C%20x86__64-purple?style=for-the-badge" alt="Platform">
</p>

<h1 align="center">Zenic-Agents v3.0.0</h1>

<p align="center"><strong>IA enjaulada. Seguridad por diseño. Determinismo garantizado.</strong></p>

<p align="center">
  La única plataforma empresarial donde la IA nunca genera — solo arbitra SÍ/NO.
</p>

<p align="center">
  <a href="./README-1.md"><strong>📖 Documentación Técnica Completa</strong></a>
</p>

---

## El Problema

Los agentes de IA actuales tienen un defecto fundamental: **confianza ciega en la generación**. Cada respuesta, cada decisión, cada línea de código que produce un LLM es una apuesta. Y las casas siempre ganan — pero aquí pierdes tú.

### Qué falla en los agentes actuales

- **Alucinaciones inevitables**: Todo LLM genera información falsa con total convicción. No es un bug, es una propiedad estadística del modelo. En un contexto empresarial, una sola alucinación puede significar una transferencia equivocada, un diagnóstico incorrecto o un contrato inválido.

- **Superficie de ataque masiva**: Cuando la IA genera código, SQL, decisiones de negocio o respuestas a clientes, cada token es un vector de ataque. No puedes auditar lo que no puedes predecir, y no puedes predecir lo que es probabilístico.

- **Dependencia de la nube**: Cada agente popular — LangChain, AutoGPT, CrewAI — requiere conexión a APIs cloud. Si se cae el servidor, se cae tu operación. Si se cae tu internet, se cae todo. Y en mercados emergentes, la conectividad no es garantía, es lujo.

- **Peso inaceptable**: Ninguno de los frameworks existentes funciona en menos de 4GB de RAM. Ninguno corre en un teléfono Android. Ninguno está diseñado para recursos limitados. Están hechos para servidores con GPU, no para la realidad de la mayoría de los negocios del mundo.

- **Cero responsabilidad**: Cuando un agente toma una mala decisión, no hay cadena de auditoría inmutable. No hay veto de seguridad inbypassable. No hay modo degradado. El sistema simplemente falla, y tú quedas responsable.

### Por qué la IA generativa sola no es suficiente

La IA generativa es extraordinaria para crear — texto, código, imágenes, análisis. Pero en un contexto empresarial, **crear sin control es un riesgo sistemático**. Un agente que puede generar una respuesta también puede generar un error. Un agente que puede ejecutar una acción también puede ejecutar la acción equivocada.

El problema no es la capacidad de la IA. Es la falta de límites arquitectónicos. Cuando la IA puede hacer cualquier cosa, eventualmente hará algo que no debería. No es una cuestión de *si*, sino de *cuándo*.

La solución no es mejor IA. Es **mejor arquitectura**: un sistema donde la IA solo pueda aprobar o rechazar, donde toda acción productiva sea determinística, y donde exista un veto de seguridad que ni la propia IA pueda sobrepasar.

---

## La Propuesta

Zenic-Agents invierte el paradigma: **la IA no genera, solo arbitra**.

### IA como árbitro binario

En Zenic-Agents, la IA (Qwen3-0.6B, CPU-only, local) tiene exactamente dos salidas posibles: **SÍ** o **NO**. No genera texto. No genera código. No genera decisiones. Solo responde a una pregunta binaria: *"Dada la evidencia, esta acción es aceptable?"*

Esto elimina las alucinaciones por diseño, no por convención:

- La IA no puede inventar datos porque no se le pide datos — se le pide un veredicto.
- La IA no puede generar código malicioso porque no genera código.
- La IA no puede tomar decisiones fuera de contexto porque solo puede aprobar o rechazar lo que el pipeline determinístico le presenta.

### Todo lo demás es determinístico

El 100% del trabajo productivo lo hacen pipelines determinísticos: clasificación por reglas, extracción por patrones, generación por templates, validación por schemas. La IA solo interviene como arbitraje final cuando el pipeline determinístico no alcanza consenso — y aun entonces, solo puede decir SÍ o NO.

```
Pipeline Determinístico (9 tareas sin IA)
    │
    ▼
Evidence Collector (evidencia a favor y en contra)
    │
    ▼
Consensus Resolver (consenso multi-señal ponderado)
    │
    ▼
Verdict Engine (IA solo si hay empate — y solo SÍ/NO)
```

Si la IA no responde, el sistema funciona con lógica determinística. Si la IA dice NO, la acción se bloquea. Si la IA dice SÍ, la acción procede con restricciones. **Nunca hay un escenario donde la IA genere algo.**

---

## Chip de Memoria Adaptativa Binaria

El corazón de v3.0.0: un motor de aprendizaje determinístico que **memoriza sin generar**.

### 3 Mecanismos de Aprendizaje

| Mecanismo | Qué hace | Ejemplo | Nivel |
|-----------|----------|---------|-------|
| **Schema Drift** | Detecta renombres de columnas DB | `estatus_cliente → estado_id` | Starter |
| **Intent Routing** | Mapea intenciones ambiguas a herramientas MCP | `tumba la cuenta → cancelar_suscripcion` | Business |
| **Policy Refinement** | Clasifica zonas grises de seguridad | `reparación urgente → gasto_crítico` | Enterprise |

### Invariante Crítico

> La Memoria **NO** altera los pesos del LLM. Modifica la configuración del DAG y las reglas del Policy Engine. "La Capa Estructurada Propone, la IA Clasifica SÍ/NO, el Humano Valida."

---

## Diferenciadores

| Diferenciador | Qué significa | Por qué importa |
|---------------|---------------|-----------------|
| **IA enjaulada (SÍ/NO)** | La IA solo emite veredictos binarios, nunca genera contenido | Elimina alucinaciones por arquitectura, no por convención |
| **Offline / CPU-only** | Funciona sin internet con Qwen3-0.6B local | Tu operación no depende de la nube ni de la conectividad |
| **Android / Termux** | Diseñado para ARM64, corre en un teléfono | Accesible para mercados donde un servidor es un lujo |
| **Motor Rust nativo** | 18+ módulos PyO3 con fallback Python | Rendimiento nativo donde importa, compatibilidad donde necesitas |
| **Safety Gate inbypassable** | Si dice DENY, no existe override — arquitectónicamente garantizado | Ningún bug, ningún agente, ningún administrador puede sobrepasar la seguridad |
| **Defensa en 6 capas** | Anti-tampering, binary hardening, cifrado, integridad, licencias, secrets | Si detecta manipulación → modo degradado (parálisis selectiva) |
| **Auditoría Merkle** | Cada acción queda registrada en un ledger inmutable con hash chains BLAKE3 | Cadena de responsabilidad criptográficamente verificable |
| **Chip de Memoria Binaria** | 3 mecanismos de aprendizaje determinístico | Aprende sin generar, sin alterar LLM, sin riesgo de alucinación |
| **500MB RAM mínimo** | Diseñado para recursos limitados | Funciona donde ningún otro framework puede |

### Lo que NO tiene nadie más

- **Doble capa de seguridad**: SafetyGate (Python) + DomainSafetyGate (Rust, 4 capas). Las reglas de dominio SOLO PUEDEN escalar veredictos — nunca degradar. Si la base dice DENY, el domain gate no puede sobreescribir.
- **35 reglas de dominio** con 8 DENY absolutos (transferencias no autorizadas, modificar recetas médicas, bypass de compliance, borrar documentos legales...). Estas acciones **no se pueden ejecutar bajo ninguna circunstancia**.
- **12 crates Rust** con 408 tests compilados en el binario — seguridad verificable, no documentable.
- **24 nichos industriales** con compliance integrado (HIPAA, PCI-DSS, GDPR, SOX, AML/KYC, COPPA, ISO 27001, SOC 2).
- **DAG Adapter inmutable**: Topología del DAG NUNCA cambia, solo los parámetros se adaptan vía middleware.
- **HITL con 3 campos obligatorios**: Justificación ≥50 chars, evidence review, risk acknowledgment con session ID crypto-linked.
- **Suscripción USDT TRC20**: 4 niveles, Saga pattern, 14-day trial, feature gates por tier.

---

## Suscripción SaaS

| Nivel | Mensual | Features Clave |
|-------|---------|----------------|
| **Starter** | $29 USDT | Pipeline básico, Schema Drift, 5 workflows, 100 acciones/día |
| **Business** | $99 USDT | Pipeline completo, +Intent Routing, 25 workflows, 1,000 acciones/día, 14-day trial |
| **Enterprise** | $299 USDT | Todo + MCP Gateway, HITL, Merkle Audit, Policy Engine, Ontología |
| **On-Premise** | $799 + $2,000 setup | Todo + Self-hosted, white-label, source code, air-gap, military encryption |

> Todos los pagos son **USDT TRC20 exclusivamente**. Sin tarjetas de crédito, sin Stripe, sin intermediarios.

---

## Pruebas

### Tests

| Componente | Tests | Ubicación |
|------------|-------|-----------|
| Workspace Rust (9 crates producción) | **408** | `zenic-v2/zenic-*/tests/` |
| PyO3 Bridge (18 módulos) | Integrados | `zenic-v2/zenic-pybridge/src/` |
| Python unitarios | **77 archivos** | `tests/unit/` |
| Python E2E | **4 suites** | `tests/e2e/` |
| Yamil Agent | **57 tests** | `tests/unit/test_yamil*.py` |
| Feature Gates | **40+ gates** | `zenic-v2/zenic-subscription/src/feature_gates.rs` |

### Safety Gate — Verificación de invariantes

El Safety Gate tiene invariantes arquitectónicos que se verifican por diseño, no por testing:

- **DENY es inmutable**: El campo `verdict` de `SafetyCheckResult` es privado con solo getters. No existe `set_verdict`. No existe mutación. Confirm y Approve rechazan acciones denegadas.
- **Las reglas solo escalan**: Domain rules solo pueden cambiar ALLOW→CONFIRM, CONFIRM→APPROVE, APPROVE→DENY. Nunca al revés. El compilador lo garantiza.
- **Rate limiting**: 30 acciones/minuto por tipo, 200/hora por categoría, 10 destructivas/hora, 20 financieras/hora. Thread-safe.

---

## Arquitectura Resumida

```
┌─────────────────────────────────────────────────┐
│                 Entrada del usuario              │
│              (TUI / API / Conversacional)        │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│            Motor de Veredicto (4 capas)          │
│                                                  │
│  1. DeterministicPipeline — 9 tareas sin IA      │
│  2. EvidenceCollector — evidencia a favor/contra │
│  3. ConsensusResolver — consenso ponderado        │
│  4. VerdictEngine — IA solo SÍ/NO si hay empate  │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│           Safety Gate (doble capa)               │
│                                                  │
│  Python: clasifica SAFE/DESTRUCTIVE/FINANCIAL    │
│  Rust: 10 reglas base + 35 de dominio +          │
│        8 estándares compliance + sensibilidad    │
│                                                  │
│  DENY → BLOQUEADO (no hay override)              │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│       Chip de Memoria Adaptativa Binaria         │
│                                                  │
│  Schema Drift · Intent Routing · Policy Refine   │
│  Knowledge Graph (SQLite) · DAG Adapter          │
│  MerkleSeal (BLAKE3) · Subscription Gate         │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│           19 Ejecutores de Acciones              │
│  DB, Email, HTTP, Webhook, File, Discord...     │
│  Todos auditados en Merkle Ledger                │
└─────────────────────────────────────────────────┘
```

### Componentes clave

- **Orquestador**: `ZenicOrchestrator` — pipeline de 8 niveles con arquitectura de veredicto
- **DAG Fractal**: 121 nodos en 3 niveles (SuperNode → SubGraph → Node) con 24 dominios de negocio
- **Chip de Memoria**: 3 mecanismos de aprendizaje, DAG Adapter inmutable, HITL con justificación obligatoria
- **Blueprints Certificados**: YAML → Template → Validación → Safety → Firma ECDSA → Blueprint certificado
- **Yamil**: Agente creador de plantillas — del nicho al blueprint certificado en un flujo unificado
- **SNA**: Sistema Nervioso Autónomo — 13 monitores proactivos sin intervención del usuario
- **Defensa**: 6 capas con scoring 0-100 y modo degradado ante manipulación
- **Distribuido**: PostgreSQL, SAGA cross-proceso, circuit breaker, leader election, work-stealing
- **Suscripción**: 4 niveles, USDT TRC20, Saga pattern, feature gates, 14-day trial

### Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Motor nativo | Rust (PyO3/maturin), BLAKE3, SQLCipher, Argon2id |
| Gateway Web | Next.js 16, TypeScript 6, Prisma 5 |
| IA | Qwen3-0.6B (CPU-only, local) — solo SÍ/NO |
| Base de datos | SQLite/SQLCipher (dev), PostgreSQL (producción) |
| Seguridad | ECDSA, PBKDF2, Fernet, anti-tampering, kill switch |
| Serialización | rkyv (tránsito), bincode (persistencia), serde_json (APIs) |
| Pagos | USDT TRC20 exclusivamente |
| Plataformas | x86_64, ARM64 (Android/Termux) |

---

## Casos de Uso

### 1. Clínica de Telemedicina (HealthTech)

Una clínica pequeña necesita gestionar citas, historiales y recetas sin infraestructura costosa. Zenic-Agents corre en un teléfono Android con Termux, protege datos médicos con compliance HIPAA integrado, y bloquea cualquier intento de modificar recetas (DENY absoluto). El Safety Gate escala automáticamente las acciones al nivel de sensibilidad **Critical** del nicho de Telemedicina.

### 2. Microfinanciera Rural (FinTech)

Una cooperativa de crédito en zona rural opera con internet intermitente. Zenic-Agents funciona offline con Qwen3 local, protege transferencias con compliance PCI-DSS y AML/KYC, y bloquea transferencias no autorizadas y bypass de compliance (2 reglas con DENY absoluto). El modo degradado garantiza operación parcial incluso con conectividad limitada.

### 3. Plataforma Educativa (EdTech)

Una plataforma de aprendizaje adaptativo para menores necesita proteger datos estudiantiles. Zenic-Agents aplica compliance COPPA y FERPA, bloquea modificación de calificaciones y filtrado de contenido educativo (DENY absoluto), y opera con el mínimo de recursos en dispositivos de bajo costo.

### 4. Inmobiliaria con Gemelos Digitales (PropTech)

Una inmobiliaria gestiona edificios inteligentes con gemelos digitales. Zenic-Agents aplica compliance BREEAM/LEED, protege datos de propiedad con GDPR y SOX, y asegura que las operaciones sobre gemelos digitales pasen por Safety Gate con sensibilidad High.

### 5. Estudio Jurídico (LegalTech)

Un estudio jurídico automatiza contratos y cumplimiento regulatorio. Zenic-Agents bloquea el borrado de documentos legales (DENY absoluto), aplica compliance SOX y eIDAS, y certifica blueprints con firma ECDSA para cadena de custodia criptográfica.

---

## Instalación y Demo

### Requisitos

- Python 3.10+
- Rust 1.85+ (opcional, para extensión nativa)
- 500MB RAM mínimo

### 3 pasos para ejecutar

```bash
# 1. Clonar e instalar
git clone https://github.com/yurislay9-ui/Zenic-Agents.git
cd Zenic-Agents && pip install -r requirements.txt

# 2. Compilar extensión Rust (opcional pero recomendado)
cd zenic-v2/zenic-pybridge && maturin develop --release && cd ../..

# 3. Iniciar
uvicorn src.server.fastapi_app:create_app_from_env --host 0.0.0.0 --port 5000 --factory
```

### Modos de ejecución

| Modo | Comando |
|------|---------|
| Servidor HTTP | `uvicorn src.server.fastapi_app:create_app_from_env --factory` |
| TUI interactiva | `python -m src.entrypoints.main` |
| Conversacional | `python -m src.entrypoints.main_conversational` |
| Headless CLI | `python -m src.entrypoints.main_headless` |

### Android / Termux

```bash
pkg install python rust
pip install -r requirements.txt
cd zenic-v2/zenic-pybridge && maturin develop --release && cd ../..
python main.py
```

### Variables esenciales

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ZENIC_ENV` | `development` | Entorno de ejecución |
| `ZENIC_PORT` | `5000` | Puerto del servidor |
| `ZENIC_DATA_DIR` | `~/.zenic-agents/data` | Directorio de datos |

---

## Roadmap

### Completado ✅

- [x] Motor Rust (PyO3) — 18+ módulos nativos con fallback Python
- [x] Workspace zenic-v2 — 12 crates (9 producción + 3 stubs)
- [x] Safety Gate doble capa — base + dominio + compliance + sensibilidad
- [x] 24 nichos industriales con compliance integrado
- [x] Arquitectura de Veredicto (4 capas) — IA solo SÍ/NO
- [x] Chip de Memoria Adaptativa Binaria — 3 mecanismos de aprendizaje
- [x] DAG Adapter — intercepción de middleware (topología inmutable)
- [x] HITL — 3 campos obligatorios (justificación ≥50 chars, evidence review, risk acknowledgment)
- [x] Blueprint certificado con firma ECDSA
- [x] Yamil — Agente creador de plantillas (57 tests)
- [x] E2E Onboarding Pipeline (8 pasos reanudable)
- [x] Defensa en 6 capas con modo degradado
- [x] Sistema Nervioso Autónomo (13 monitores)
- [x] 19 ejecutores de acciones con auditoría Merkle
- [x] Sistema de Suscripción SaaS — USDT TRC20, Saga pattern, feature gates
- [x] Gateway TypeScript — Next.js 16, 80+ API routes
- [x] Sistema distribuido (PostgreSQL, SAGA, circuit breaker)
- [x] API OpenAI-compatible (drop-in para Cline/Aide/OpenCode)
- [x] Plan Definitivo V3 — 47/47 requisitos aprobados
- [x] 3 Grietas reparadas (DAG interception, 9-step pipeline, HITL mandatory fields)

### En progreso 🔄

- [ ] Fases 3-5 del plan de implementación
- [ ] Nombres de nichos en español (traducción cross-cutting)
- [ ] Benchmarks de rendimiento (`zenic-bench`)
- [ ] Fix 3 duplicaciones Phase 4

### Pendiente ❌

- [ ] Tests de integración del workspace (`zenic-tests`)
- [ ] FFI C interface (`zenic-ffi`) — bindings para otros lenguajes
- [ ] Demos interactivas y screenshots
- [ ] Casos de estudio documentados con métricas reales
- [ ] Documentación de API completa (OpenAPI/Swagger)
- [ ] CI/CD con tests automáticos en ARM64
- [ ] Marketplace de Blueprints certificados
- [ ] Plugin SDK para terceros

---

## Comparativa

| | **Zenic-Agents** | LangChain | AutoGPT | CrewAI |
|---|---|---|---|---|
| IA solo SÍ/NO | **Sí** | No | No | No |
| Alucinaciones | **Imposibles** | Riesgo constante | Riesgo constante | Riesgo constante |
| Offline / CPU | **Sí** | No | No | No |
| Android/Termux | **Sí** | No | No | No |
| Motor Rust nativo | **18+ módulos** | No | No | No |
| Safety Gate inbypassable | **Doble capa** | No | No | No |
| Anti-tampering | **6 capas** | No | No | No |
| Compliance integrado | **8 estándares** | No | No | No |
| 500MB RAM | **Diseñado para eso** | Pesado | Muy pesado | Pesado |
| Auditoría Merkle | **Sí** | No | No | No |
| API OpenAI-compatible | **Drop-in** | Framework | No | No |
| Chip de Memoria | **3 mecanismos** | No | No | No |
| Suscripción USDT TRC20 | **4 niveles** | No | No | No |

---

## Licencia

Propietaria. Todos los derechos reservados. El uso requiere licencia válida firmada con ECDSA.

---

<p align="center">
  <strong>Zenic-Agents v3.0.0</strong> — IA enjaulada. Seguridad por diseño. Determinismo garantizado.
</p>
