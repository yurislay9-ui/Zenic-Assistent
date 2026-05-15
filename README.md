<p align="center">
  <img src="https://img.shields.io/badge/version-3.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/Rust-PyO3-orange?style=for-the-badge" alt="Rust+PyO3">
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Platform-ARM64%20%7C%20x86__64-purple?style=for-the-badge" alt="Platform">
</p>

<h1 align="center">Zenic-Agents</h1>

<p align="center"><strong>IA enjaulada. Seguridad por diseno. Determinismo garantizado.</strong></p>

<p align="center">
  La unica plataforma empresarial donde la IA nunca genera — solo arbitra SÍ/NO.
</p>

---

## El Problema

Los agentes de IA actuales tienen un defecto fundamental: **confianza ciega en la generacion**. Cada respuesta, cada decision, cada linea de codigo que produce un LLM es una apuesta. Y las casas siempre ganan — pero aqui pierdes tu.

### Que falla en los agentes actuales

- **Alucinaciones inevitables**: Todo LLM genera informacion falsa con total conviccion. No es un bug, es una propiedad estadistica del modelo. En un contexto empresarial, una sola alucinacion puede significar una transferencia equivocada, un diagnostico incorrecto o un contrato invalido.

- **Superficie de ataque masiva**: Cuando la IA genera codigo, SQL, decisiones de negocio o respuestas a clientes, cada token es un vector de ataque. No puedes auditar lo que no puedes predecir, y no puedes predecir lo que es probabilistico.

- **Dependencia de la nube**: Cada agente popular — LangChain, AutoGPT, CrewAI — requiere conexion a APIs cloud. Si se cae el servidor, se cae tu operacion. Si se cae tu internet, se cae todo. Y en mercados emergentes, la conectividad no es garantia, es lujo.

- **Peso inaceptable**: Ninguno de los frameworks existentes funciona en menos de 4GB de RAM. Ninguno corre en un telefono Android. Ninguno esta disenado para recursos limitados. Estan hechos para servidores con GPU, no para la realidad de la mayoria de los negocios del mundo.

- **Cero responsabilidad**: Cuando un agente toma una mala decision, no hay cadena de auditoria inmutable. No hay veto de seguridad inbypassable. No hay modo degradado. El sistema simplemente falla, y tu quedas responsable.

### Por que la IA generativa sola no es suficiente

La IA generativa es extraordinaria para crear — texto, codigo, imagenes, analisis. Pero en un contexto empresarial, **crear sin control es un riesgo sistematico**. Un agente que puede generar una respuesta tambien puede generar un error. Un agente que puede ejecutar una accion tambien puede ejecutar la accion equivocada.

El problema no es la capacidad de la IA. Es la falta de limites arquitectonicos. Cuando la IA puede hacer cualquier cosa, eventualmente hara algo que no deberia. No es una cuestion de *si*, sino de *cuando*.

La solucion no es mejor IA. Es **mejor arquitectura**: un sistema donde la IA solo pueda aprobar o rechazar, donde toda accion productiva sea deterministica, y donde exista un veto de seguridad que ni la propia IA pueda sobrepasar.

---

## La Propuesta

Zenic-Agents invierte el paradigma: **la IA no genera, solo arbitra**.

### IA como arbitro binario

En Zenic-Agents, la IA (Qwen3-0.6B, CPU-only, local) tiene exactamente dos salidas posibles: **SÍ** o **NO**. No genera texto. No genera codigo. No genera decisiones. Solo responde a una pregunta binaria: *"Dada la evidencia, esta accion es aceptable?"*

Esto elimina las alucinaciones por diseno, no por convencion:

- La IA no puede inventar datos porque no se le pide datos — se le pide un veredicto.
- La IA no puede generar codigo malicioso porque no genera codigo.
- La IA no puede tomar decisiones fuera de contexto porque solo puede aprobar o rechazar lo que el pipeline deterministico le presenta.

### Todo lo demas es deterministico

El 100% del trabajo productivo lo hacen pipelines deterministicos: clasificacion por reglas, extraccion por patrones, generacion por templates, validacion por schemas. La IA solo interviene como arbitraje final cuando el pipeline deterministico no alcanza consenso — y aun entonces, solo puede decir SÍ o NO.

```
Pipeline Deterministico (7 tareas sin IA)
    |
    v
Evidence Collector (evidencia a favor y en contra)
    |
    v
Consensus Resolver (consenso multi-senal ponderado)
    |
    v
Verdict Engine (IA solo si hay empate — y solo SÍ/NO)
```

Si la IA no responde, el sistema funciona con logica deterministica. Si la IA dice NO, la accion se bloquea. Si la IA dice SÍ, la accion procede con restricciones. **Nunca hay un escenario donde la IA genere algo.**

---

## Diferenciadores

| Diferenciador | Que significa | Por que importa |
|---------------|---------------|-----------------|
| **IA enjaulada (SÍ/NO)** | La IA solo emite veredictos binarios, nunca genera contenido | Elimina alucinaciones por arquitectura, no por convencion |
| **Offline / CPU-only** | Funciona sin internet con Qwen3-0.6B local | Tu operacion no depende de la nube ni de la conectividad |
| **Android / Termux** | Disenado para ARM64, corre en un telefono | Accesible para mercados donde un servidor es un lujo |
| **Motor Rust nativo** | 18+ modulos PyO3 con fallback Python | Rendimiento nativo donde importa, compatibilidad donde necesitas |
| **Safety Gate inbypassable** | Si dice DENY, no existe override — arquitectonicamente garantizado | Ningun bug, ningun agente, ningun administrador puede sobrepasar la seguridad |
| **Defensa en 6 capas** | Anti-tampering, binary hardening, cifrado, integridad, licencias, secrets | Si detecta manipulacion → modo degradado (paralisis selectiva) |
| **Auditoria Merkle** | Cada accion queda registrada en un ledger inmutable con hash chains | Cadena de responsabilidad criptograficamente verificable |
| **500MB RAM minimo** | Disenado para recursos limitados | Funciona donde ningun otro framework puede |

### Lo que NO tiene nadie mas

- **Doble capa de seguridad**: SafetyGate (Python) + DomainSafetyGate (Rust, 4 capas). Las reglas de dominio SOLO PUEDEN escalar veredictos — nunca degradar. Si la base dice DENY, el domain gate no puede sobreescribir.
- **35 reglas de dominio** con 8 DENY absolutos (transferencias no autorizadas, modificar recetas medicas, bypass de compliance, borrar documentos legales...). Estas acciones **no se pueden ejecutar bajo ninguna circunstancia**.
- **10 crates Rust** con 408 tests compilados en el binario — seguridad verificable, no documentable.
- **24 nichos industriales** con compliance integrado (HIPAA, PCI-DSS, GDPR, SOX, AML/KYC, COPPA, ISO 27001, SOC 2).

---

## Pruebas

### Tests

| Componente | Tests | Ubicacion |
|------------|-------|-----------|
| Workspace Rust (7 crates completos) | **408** | `zenic-v2/zenic-*/tests/` |
| PyO3 Bridge (18 modulos) | Integrados | `zenic-v2/zenic-pybridge/src/` |
| Python unitarios | **77 archivos** | `tests/unit/` |
| Python E2E | **4 suites** | `tests/e2e/` |
| Yamil Agent | **57 tests** | `tests/unit/test_yamil*.py` |

### Safety Gate — Verificacion de invariantes

El Safety Gate tiene invariantes arquitectonicos que se verifican por diseno, no por testing:

- **DENY es inmutable**: El campo `verdict` de `SafetyCheckResult` es privado con solo getters. No existe `set_verdict`. No existe mutacion. Confirm y Approve rechazan acciones denegadas.
- **Las reglas solo escalan**: Domain rules solo pueden cambiar ALLOW→CONFIRM, CONFIRM→APPROVE, APPROVE→DENY. Nunca al reves. El compilador lo garantiza.
- **Rate limiting**: 30 acciones/minuto por tipo, 200/hora por categoria, 10 destructivas/hora, 20 financieras/hora. Thread-safe.

### Benchmarks

Los benchmarks de rendimiento estan en `zenic-v2/zenic-bench/` (stub, pendiente de Phase 8). Los modulos criticos de rendimiento (crypto, hash, db) estan implementados en Rust nativo con PyO3.

---

## Arquitectura Resumida

```
┌─────────────────────────────────────────────────┐
│                 Entrada del usuario              │
│              (TUI / API / Conversacional)        │
└──────────────────────┬──────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────┐
│            Motor de Veredicto (4 capas)          │
│                                                  │
│  1. DeterministicPipeline — 7 tareas sin IA      │
│  2. EvidenceCollector — evidencia a favor/contra │
│  3. ConsensusResolver — consenso ponderado        │
│  4. VerdictEngine — IA solo SÍ/NO si hay empate  │
└──────────────────────┬──────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────┐
│           Safety Gate (doble capa)               │
│                                                  │
│  Python: clasifica SAFE/DESTRUCTIVE/FINANCIAL    │
│  Rust: 10 reglas base + 35 de dominio +          │
│        8 estandares compliance + sensibilidad    │
│                                                  │
│  DENY → BLOQUEADO (no hay override)              │
└──────────────────────┬──────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────┐
│           19 Ejecutores de Acciones              │
│  DB, Email, HTTP, Webhook, File, Discord...     │
│  Todos auditados en Merkle Ledger                │
└─────────────────────────────────────────────────┘
```

### Componentes clave

- **Orquestador**: `ZenicOrchestrator` — pipeline de 8 niveles con arquitectura de veredicto
- **DAG Fractal**: 121 nodos en 3 niveles (SuperNode → SubGraph → Node) con 24 dominios de negocio
- **Blueprints Certificados**: YAML → Template → Validacion → Safety → Firma ECDSA → Blueprint certificado
- **Yamil**: Agente creador de plantillas — del nicho al blueprint certificado en un flujo unificado
- **SNA**: Sistema Nervioso Autonomo — 13 monitores proactivos sin intervencion del usuario
- **Defensa**: 6 capas con scoring 0-100 y modo degradado ante manipulacion
- **Distribuido**: PostgreSQL, SAGA cross-proceso, circuit breaker, leader election, work-stealing

### Stack

| Capa | Tecnologia |
|------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Motor nativo | Rust (PyO3/maturin), BLAKE3, SQLCipher, Argon2id |
| IA | Qwen3-0.6B (CPU-only, local) — solo SÍ/NO |
| Base de datos | SQLite/SQLCipher (dev), PostgreSQL (produccion) |
| Seguridad | ECDSA, PBKDF2, Fernet, anti-tampering, kill switch |
| Plataformas | x86_64, ARM64 (Android/Termux) |

---

## Casos de Uso

### 1. Clinica de Telemedicina (HealthTech)

Una clinica pequena necesita gestionar citas, historiales y recetas sin infraestructura costosa. Zenic-Agents corre en un telefono Android con Termux, protege datos medicos con compliance HIPAA integrado, y bloquea cualquier intento de modificar recetas (DENY absoluto). El Safety Gate escala automaticamente las acciones al nivel de sensibilidad **Critical** del nicho de Telemedicina.

### 2. Microfinanciera Rural (FinTech)

Una cooperativa de credito en zona rural opera con internet intermitente. Zenic-Agents funciona offline con Qwen3 local, protege transferencias con compliance PCI-DSS y AML/KYC, y bloquea transferencias no autorizadas y bypass de compliance (2 reglas con DENY absoluto). El modo degradado garantiza operacion parcial incluso con conectividad limitada.

### 3. Plataforma Educativa (EdTech)

Una plataforma de aprendizaje adaptativo para menores necesita proteger datos estudiantiles. Zenic-Agents aplica compliance COPPA y FERPA, bloquea modificacion de calificaciones y filtrado de contenido educativo (DENY absoluto), y opera con el minimo de recursos en dispositivos de bajo costo.

### 4. Inmobiliaria con Gemelos Digitales (PropTech)

Una inmobiliaria gestiona edificios inteligentes con gemelos digitales. Zenic-Agents aplica compliance BREEAM/LEED, protege datos de propiedad con GDPR y SOX, y asegura que las operaciones sobre gemelos digitales pasen por Safety Gate con sensibilidad High.

### 5. Estudio Juridico (LegalTech)

Un estudio juridico automatiza contratos y cumplimiento regulatorio. Zenic-Agents bloquea el borrado de documentos legales (DENY absoluto), aplica compliance SOX y eIDAS, y certifica blueprints con firma ECDSA para cadena de custodia criptografica.

---

## Instalacion y Demo

### Requisitos

- Python 3.10+
- Rust 1.85+ (opcional, para extension nativa)
- 500MB RAM minimo

### 3 pasos para ejecutar

```bash
# 1. Clonar e instalar
git clone https://github.com/yurislay9-ui/Zenic-Agents.git
cd Zenic-Agents && pip install -r requirements.txt

# 2. Compilar extension Rust (opcional pero recomendado)
cd zenic-v2/zenic-pybridge && maturin develop --release && cd ../..

# 3. Iniciar
uvicorn src.server.fastapi_app:create_app_from_env --host 0.0.0.0 --port 5000 --factory
```

### Modos de ejecucion

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

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `ZENIC_ENV` | `development` | Entorno de ejecucion |
| `ZENIC_PORT` | `5000` | Puerto del servidor |
| `ZENIC_DATA_DIR` | `~/.zenic-agents/data` | Directorio de datos |

---

## Roadmap

### Completado

- [x] Motor Rust (PyO3) — 18+ modulos nativos con fallback Python
- [x] Workspace zenic-v2 — 7 crates completos con 408 tests
- [x] Safety Gate doble capa — base + dominio + compliance + sensibilidad
- [x] 24 nichos industriales con compliance integrado
- [x] Arquitectura de Veredicto (4 capas) — IA solo SÍ/NO
- [x] Blueprint certificado con firma ECDSA
- [x] Yamil — Agente creador de plantillas (57 tests)
- [x] E2E Onboarding Pipeline (8 pasos resumible)
- [x] Defensa en 6 capas con modo degradado
- [x] Sistema Nervioso Autonomo (13 monitores)
- [x] 19 ejecutores de acciones con auditoria Merkle
- [x] Billing SaaS con Stripe
- [x] Sistema distribuido (PostgreSQL, SAGA, circuit breaker)
- [x] API OpenAI-compatible (drop-in para Cline/Aide/OpenCode)
- [x] UI Web (HTMX/Alpine/Chart.js)

### En progreso

- [ ] Nombres de nichos en espanol (traduccion cross-cutting)
- [ ] Benchmarks de rendimiento (`zenic-bench`)

### Pendiente

- [ ] Tests de integracion del workspace (`zenic-tests`)
- [ ] FFI C interface (`zenic-ffi`) — bindings para otros lenguajes
- [ ] Demos interactivas y screenshots
- [ ] Casos de estudio documentados con metricas reales
- [ ] Documentacion de API completa (OpenAPI/Swagger)
- [ ] CI/CD con tests automaticos en ARM64
- [ ] Marketplace de Blueprints certificados
- [ ] Plugin SDK para terceros

---

## Comparativa

| | **Zenic-Agents** | LangChain | AutoGPT | CrewAI |
|---|---|---|---|---|
| IA solo SÍ/NO | **Si** | No | No | No |
| Alucinaciones | **Imposibles** | Riesgo constante | Riesgo constante | Riesgo constante |
| Offline / CPU | **Si** | No | No | No |
| Android/Termux | **Si** | No | No | No |
| Motor Rust nativo | **18+ modulos** | No | No | No |
| Safety Gate inbypassable | **Doble capa** | No | No | No |
| Anti-tampering | **6 capas** | No | No | No |
| Compliance integrado | **8 estandares** | No | No | No |
| 500MB RAM | **Disenado para eso** | Pesado | Muy pesado | Pesado |
| Auditoria Merkle | **Si** | No | No | No |
| API OpenAI-compatible | **Drop-in** | Framework | No | No |

---

## Licencia

Propietaria. Todos los derechos reservados. El uso requiere licencia valida firmada con ECDSA.

---

<p align="center">
  <strong>Zenic-Agents</strong> — IA enjaulada. Seguridad por diseno. Determinismo garantizado.
</p>
