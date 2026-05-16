<p align="center">
  <img src="https://img.shields.io/badge/version-3.0.0-blue?style=for-the-badge" alt="Version">
  <img src="https://img.shields.io/badge/Rust-PyO3_12_Crates-orange?style=for-the-badge" alt="Rust+PyO3">
  <img src="https://img.shields.io/badge/Python-3.10+-green?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/TypeScript-Next.js_16-blue?style=for-the-badge" alt="TypeScript">
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/Platform-ARM64%20%7C%20x86__64-purple?style=for-the-badge" alt="Platform">
</p>

<h1 align="center">Zenic-Agents v3.0.0 — Documentación Técnica Completa</h1>

<p align="center"><strong>IA enjaulada. Seguridad por diseño. Determinismo garantizado.</strong></p>

<p align="center">
  La única plataforma empresarial donde la IA nunca genera — solo arbitra SÍ/NO.
</p>

---

## Tabla de Contenidos

- [1. Visión General](#1-visión-general)
- [2. Principios Arquitectónicos](#2-principios-arquitectónicos)
- [3. Chip de Memoria Adaptativa Binaria](#3-chip-de-memoria-adaptativa-binaria)
- [4. Motor de Veredicto — 4 Capas](#4-motor-de-veredicto--4-capas)
- [5. Pipeline Determinístico — 9 Pasos](#5-pipeline-determinístico--9-pasos)
- [6. DAG Adapter — Intercepción de Middleware](#6-dag-adapter--intercepción-de-middleware)
- [7. HITL — Human-in-the-Loop con 3 Campos Obligatorios](#7-hitl--human-in-the-loop-con-3-campos-obligatorios)
- [8. Sistema de Suscripción SaaS](#8-sistema-de-suscripción-saas)
- [9. Feature Gates — Control de Acceso por Nivel](#9-feature-gates--control-de-acceso-por-nivel)
- [10. Workspace Rust — 12 Crates](#10-workspace-rust--12-crates)
- [11. PyO3 Bridge — Módulo \_zenic\_native](#11-pyo3-bridge--módulo-_zenic_native)
- [12. Codebase Python — 30+ Subsistemas](#12-codebase-python--30-subsistemas)
- [13. Gateway TypeScript — Next.js 16 + Prisma](#13-gateway-typescript--nextjs-16--prisma)
- [14. Serialización — rkyv + bincode + serde\_json](#14-serialización--rkyv--bincode--serde_json)
- [15. MerkleLedger — Auditoría Inmutable BLAKE3](#15-merkleledger--auditoría-inmutable-blake3)
- [16. Safety Gate — Doble Capa Inbypassable](#16-safety-gate--doble-capa-inbypassable)
- [17. 19 Ejecutores de Acciones](#17-19-ejecutores-de-acciones)
- [18. 24 Nichos Industriales](#18-24-nichos-industriales)
- [19. Defensa en 6 Capas](#19-defensa-en-6-capas)
- [20. Sistema Nervioso Autónomo (SNA)](#20-sistema-nervioso-autónomo-sna)
- [21. Sistema Distribuido](#21-sistema-distribuido)
- [22. Blueprints Certificados](#22-blueprints-certificados)
- [23. Yamil — Agente Creador de Plantillas](#23-yamil--agente-creador-de-plantillas)
- [24. Patrones de Diseño (18 Módulos)](#24-patrones-de-diseño-18-módulos)
- [25. Motor Conversacional](#25-motor-conversacional)
- [26. Sistema de Plugins](#26-sistema-de-plugins)
- [27. Canales de Notificación](#27-canales-de-notificación)
- [28. Autopilot y ROI](#28-autopilot-y-roi)
- [29. Observabilidad](#29-observabilidad)
- [30. Playbooks](#30-playbooks)
- [31. Policy Engine (DSL)](#31-policy-engine-dsl)
- [32. Caos Engineering](#32-caos-engineering)
- [33. Infraestructura de Tests](#33-infraestructura-de-tests)
- [34. Stack Tecnológico Completo](#34-stack-tecnológico-completo)
- [35. Estructura de Directorios](#35-estructura-de-directorios)
- [36. Mapa Completo de Features por Nivel de Suscripción](#36-mapa-completo-de-features-por-nivel-de-suscripción)
- [37. 3 Grietas Reparadas](#37-3-grietas-reparadas)
- [38. Plan de Implementación — 5 Fases](#38-plan-de-implementación--5-fases)
- [39. API Routes — 80+ Endpoints](#39-api-routes--80-endpoints)
- [40. Invariantes del Sistema](#40-invariantes-del-sistema)
- [41. Restricciones de Plataforma](#41-restricciones-de-plataforma)
- [42. Instalación y Ejecución](#42-instalación-y-ejecución)
- [43. Variables de Entorno](#43-variables-de-entorno)
- [44. Comparativa con Frameworks Existentes](#44-comparativa-con-frameworks-existentes)
- [45. Roadmap](#45-roadmap)
- [46. Licencia](#46-licencia)

---

## 1. Visión General

**Zenic-Agents v3.0.0** es una plataforma empresarial de IA híbrida (Python + Rust + TypeScript) donde la IA **nunca genera contenido** — solo arbitra SÍ/NO. Toda acción productiva es ejecutada por pipelines determinísticos. La IA (Qwen3-0.6B, CPU-only, local) solo interviene como árbitro binario cuando el pipeline no alcanza consenso.

### Métricas del Proyecto

| Métrica | Valor |
|---------|-------|
| Versión | 3.0.0 |
| Crates Rust | 12 (9 producción + 3 stubs) |
| Módulos PyO3 | 18+ |
| Tests Rust | 408+ |
| Tests Python | 77 archivos, 28+ directorios |
| API Routes | 80+ |
| Ejecutores | 19 |
| Nichos industriales | 24 |
| Feature Gates | 40+ (Rust) + 80+ (TypeScript) |
| Reglas de dominio | 35 (8 DENY absolutos) |
| Estándares compliance | 8+ |
| Patrones de diseño | 18 módulos |
| Monitores SNA | 13 |
| Capas de defensa | 6 |

---

## 2. Principios Arquitectónicos

1. **La Capa Estructurada Propone, la IA Clasifica SÍ/NO, el Humano Valida** — El pipeline determinístico genera hipótesis, la IA solo responde YES/NO, el humano aprueba con justificación obligatoria.

2. **LLM NUNCA genera contenido** — Solo emite veredicto binario. No genera texto, código, decisiones ni datos. Este es un invariante arquitectónico, no una convención.

3. **La Memoria NO altera pesos del LLM** — Modifica configuración del DAG y reglas del Policy Engine. El Chip de Memoria es binario: propone, no genera.

4. **Offline, CPU-only, ARM64, 500MB RAM** — Diseñado para funcionar sin internet, sin GPU, en un teléfono Android con Termux.

5. **rkyv para tránsito (zero-copy), bincode para persistencia, serde_json solo para APIs** — Estrategia de serialización de 3 capas optimizada para rendimiento.

6. **DENY es inmutable** — Si el Safety Gate dice DENY, no existe override. Arquitectónicamente garantizado por el compilador Rust.

7. **Reglas solo escalan** — Domain rules solo pueden cambiar ALLOW→CONFIRM→APPROVE→DENY. Nunca al revés. El compilador lo garantiza.

---

## 3. Chip de Memoria Adaptativa Binaria

El **Chip de Memoria Adaptativa Binaria** es el motor de aprendizaje determinístico de Zenic-Agents. Implementado en el crate `zenic-memory` (16 archivos fuente), proporciona 3 mecanismos de aprendizaje que alimentan un Knowledge Graph Determinístico en SQLite.

### 3 Mecanismos de Aprendizaje

| Mecanismo | Descripción | Ejemplo | Nivel Mínimo |
|-----------|-------------|---------|---------------|
| **Schema Drift** | Renombramiento de columnas DB | `estatus_cliente → estado_id` | Starter |
| **Intent Routing** | Matching de intención ambigua → herramienta MCP | `tumba la cuenta → cancelar_suscripcion` | Business |
| **Policy Refinement** | Clasificación de zonas grises | `reparación urgente → gasto_crítico` | Enterprise |

### Grafo Híbrido

- **Per-tenant**: Grafo aislado por tenant con mapeos semánticos propios
- **Ontology Base**: Grafo compartido con mapeos predefinidos (opt-in, sobreescribible localmente)
- **3 Tablas SQLite**: `semantic_mappings`, `ontology_base`, `learning_audit`

### Estructura del Crate zenic-memory

```
zenic-memory/
├── lib.rs              — Punto de entrada del crate
├── types.rs            — Tipos core: SemanticMapping, LearningVerdict, MemoryApprovalRequest
├── graph.rs            — Knowledge Graph Determinístico (SQLite)
├── cache.rs            — LRU Cache por tier (100/500/2000/∞)
├── ontology.rs         — Ontología compartida + híbrida
├── hypothesis.rs       — Generador de hipótesis (pre-IA)
├── schema_drift.rs     — Mecanismo 1: Schema Drift
├── intent_routing.rs   — Mecanismo 2: Intent Routing
├── policy_refinement.rs— Mecanismo 3: Policy Refinement
├── dag_adapter.rs      — Intercepción de middleware DAG (GRIETA 1)
├── verdict_adapter.rs  — Adaptador al Motor de Veredicto
├── hitl_bridge.rs      — Puente HITL para aprobaciones
├── merkle_seal.rs      — Sello BLAKE3 para mappings aprobados
├── yaml_renderer.rs    — Render YAML para aprobaciones
├── subscription_gate.rs— Feature gates por tier
├── lifecycle.rs        — Ciclo de vida del aprendizaje
└── errors.rs           — Taxonomía de errores
```

---

## 4. Motor de Veredicto — 4 Capas

El Motor de Veredicto implementa una arquitectura de 4 capas donde la IA solo interviene en la capa 4 y únicamente cuando hay empate o fallo de consenso.

```
┌─────────────────────────────────────────────────────┐
│  Capa 1: DeterministicPipeline                      │
│  9 tareas sin IA — clasificación, extracción,       │
│  validación, enrutamiento, simulación               │
├─────────────────────────────────────────────────────┤
│  Capa 2: EvidenceCollector                          │
│  Recopila evidencia a favor y en contra             │
│  de la acción propuesta                             │
├─────────────────────────────────────────────────────┤
│  Capa 3: ConsensusResolver                          │
│  Consenso multi-señal ponderado                     │
│  Si hay consenso → veredicto final                  │
├─────────────────────────────────────────────────────┤
│  Capa 4: VerdictEngine (IA)                         │
│  Solo si hay empate o fallo de consenso             │
│  La IA solo puede decir SÍ o NO                     │
└─────────────────────────────────────────────────────┘
```

### Disponibilidad por Tier

| Capa | Starter | Business | Enterprise | On-Premise |
|------|---------|----------|------------|------------|
| L1: DeterministicPipeline | ✓ (parcial) | ✓ (completo) | ✓ | ✓ |
| L2: EvidenceCollector | ✗ | ✓ | ✓ | ✓ |
| L3: ConsensusResolver | ✗ | ✓ | ✓ | ✓ |
| L4: VerdictEngine (IA) | ✗ | ✗ | ✓ | ✓ |

---

## 5. Pipeline Determinístico — 9 Pasos

El pipeline determinístico ejecuta 9 tareas secuenciales sin intervención de IA. La IA solo se invoca si el ConsensusResolver no alcanza consenso.

| Paso | Tarea | Descripción | Origen |
|------|-------|-------------|--------|
| 1 | `memory_lookup` | Búsqueda en Knowledge Graph SQLite | GRIETA 2 |
| 2 | `classify_intent` | Clasificación de intención por reglas | Original |
| 3 | `extract_entities` | Extracción de entidades por patrones | Original |
| 4 | `validate_schema` | Validación contra schemas definidos | Original |
| 5 | `dag_node_adapt` | Adaptación de nodo DAG con memoria | GRIETA 2 |
| 6 | `check_rbac_policies` | Verificación RBAC de políticas | Original |
| 7 | `gather_context` | Recopilación de contexto relevante | Original |
| 8 | `route_mcp_tool` | Enrutamiento a herramienta MCP | Original |
| 9 | `simulate_dry_run` | Simulación dry-run de la acción | Original |

### Disponibilidad por Tier

| Pasos | Starter | Business | Enterprise | On-Premise |
|-------|---------|----------|------------|------------|
| 1-4 | ✓ | ✓ | ✓ | ✓ |
| 5 (dag_node_adapt) | ✗ | ✓ | ✓ | ✓ |
| 6-8 | ✗ | ✓ | ✓ | ✓ |
| 9 (simulate_dry_run) | ✗ | ✗ | ✓ | ✓ |

---

## 6. DAG Adapter — Intercepción de Middleware

**GRIETA 1 Reparada**: El `dag_adapter.rs` implementa intercepción de middleware en el DAG.

### Comportamiento

1. Si un nodo DAG falla → pausa la ejecución
2. Consulta SQLite (Knowledge Graph) para mappings aprobados
3. Si encuentra mapping → inyecta parámetro corregido
4. Re-ejecuta el nodo instantáneamente

### Invariante Crítico

- **Topología del DAG es INMUTABLE** — No se pueden agregar, eliminar o reordenar nodos
- **Parámetros son flexibles** — El adapter solo modifica parámetros de ejecución, nunca la estructura

```
Nodo Falla → Pause → Lookup Memory → Inject Corrected Param → Re-execute
     ↑                                                    │
     └──────── Si no hay mapping → HITL Approval ─────────┘
```

---

## 7. HITL — Human-in-the-Loop con 3 Campos Obligatorios

**GRIETA 3 Reparada**: El HITL requiere 3 campos obligatorios tipados para cualquier aprobación. La compilación YAML FALLA si no se completan.

### Campos Obligatorios

| Campo | Tipo | Restricción | Propósito |
|-------|------|-------------|-----------|
| `admin_evidence_review` | `bool` | Debe ser `true` | Admin confirma revisión de evidencia de L2 y L3 |
| `admin_justification` | `String` | Mínimo 50 caracteres | Justificación de por qué el mapping es válido — no se permite "ok" |
| `risk_acknowledgment` | `bool + admin_session_id` | Ambos obligatorios | Admin asume responsabilidad con sesión crypto-linked |

### Estructura MemoryApprovalRequest (Rust)

```rust
pub struct MemoryApprovalRequest {
    pub admin_evidence_review: bool,      // MUST be true
    pub admin_justification: String,      // MUST be ≥50 chars
    pub risk_acknowledgment: bool,        // MUST be true
    pub admin_session_id: String,         // MUST be non-empty, crypto-linked
    pub mapping_id: String,               // Auto-populated
    pub ia_question: String,              // Auto-populated
    pub ia_response: bool,                // Auto-populated
    pub evidence_for: Vec<String>,        // Auto-populated from L2
    pub evidence_against: Vec<String>,    // Auto-populated from L2
    pub consensus_score: f64,             // Auto-populated from L3
}
```

---

## 8. Sistema de Suscripción SaaS

El sistema de suscripción está implementado en **3 stacks**: Rust (`zenic-subscription`), TypeScript (Gateway) y Python (API routes). Todos los pagos son **USDT TRC20 exclusivamente**.

### 4 Niveles de Suscripción

| Nivel | Mensual | Anual (10 meses) | Setup Fee | Trial |
|-------|---------|-------------------|-----------|-------|
| **Starter** | $29 USDT | $290 USDT | $0 | — |
| **Business** | $99 USDT | $990 USDT | $0 | 14 días (default) |
| **Enterprise** | $299 USDT | $2,990 USDT | $0 | — |
| **On-Premise Enterprise** | $799 USDT | $7,990 USDT | $2,000 | — |

### Add-Ons Disponibles

| Add-On | Mensual | Tiers Compatibles |
|--------|---------|-------------------|
| Extra Workflows (+10) | $10 | Starter, Business |
| Extra Team Members (+5) | $15 | Starter, Business |
| Advanced Analytics | $25 | Starter, Business |
| Policy Engine | $30 | Business |
| HITL Approvals | $35 | Business |

### Ciclo de Vida de la Suscripción

```
Trial(14d) → Active → PastDue → Cancelled
                    ↘ Expired
Active → Suspended → Active
Active → Downgraded → Active
```

### Flujo de Pago (USDT TRC20)

1. Crear pago pendiente → dirección wallet de la empresa
2. Usuario envía USDT TRC20, envía `tx_hash` (64 hex chars)
3. Admin confirma (Manual) o semi-auto (SemiManual)
4. **PaymentSaga**: `verify_payment → apply_subscription → grant_access → update_audit`

### Saga Pattern — 6 Flujos Transaccionales

| Saga | Pasos |
|------|-------|
| **SignupSaga** | `validate_user → create_trial → activate_trial → notify_user` |
| **PaymentSaga** | `verify_payment → apply_subscription → grant_access → update_audit` |
| **CancellationSaga** | `revoke_access → cancel_subscription → process_refund → notify_user` |
| **RenewalSaga** | `verify_renewal → extend_subscription → update_audit → notify_user` |
| **UpgradeSaga** | `validate_upgrade → calculate_proration → verify_payment → apply_new_tier → update_access → update_audit` |

### Límites por Tier

| Límite | Starter | Business | Enterprise | On-Premise |
|--------|---------|----------|------------|------------|
| Workflows | 5 | 25 | ∞ | ∞ |
| Acciones/día | 100 | 1,000 | ∞ | ∞ |
| Team Members | 3 | 15 | ∞ | ∞ |
| API calls/min | 30 | 100 | 1,000 | ∞ |
| Storage (MB) | 500 | 5,000 | ∞ | ∞ |
| Sesiones concurrentes | 2 | 10 | ∞ | ∞ |
| Playbooks | 3 | 25 | ∞ | ∞ |
| Policy Rules | 10 | 50 | ∞ | ∞ |
| Approval Chain Depth | 0 | 3 | 10 | ∞ |
| Custom Playbooks | ✗ | ✗ | ✓ | ✓ |
| Full Observability | ✗ | ✗ | ✓ | ✓ |
| Policy Engine | ✗ | ✓ | ✓ | ✓ |
| HITL Approvals | ✗ | ✗ | ✓ | ✓ |
| Merkle Audit | ✗ | ✗ | ✓ | ✓ |
| Self-Hosted | ✗ | ✗ | ✗ | ✓ |

### Memory Chip — Límites por Tier

| Recurso | Starter | Business | Enterprise | On-Premise |
|---------|---------|----------|------------|------------|
| Mecanismos | Schema Drift | +Intent Routing | +Policy Refinement | All + Custom |
| Mappings/mes | 10 | 50 | ∞ | ∞ |
| LRU Cache | 100 | 500 | 2,000 | ∞ |
| Ontología | ✗ | ✗ | ✓ | ✓ |
| Export/Import | ✗ | ✗ | ✗ | ✓ |
| Custom Ontología | ✗ | ✗ | ✗ | ✓ |

---

## 9. Feature Gates — Control de Acceso por Nivel

Los Feature Gates son el mecanismo de control de acceso que mapea cada funcionalidad a su nivel de suscripción mínimo. Implementado en Rust (`zenic-subscription/feature_gates.rs`) y TypeScript (`gateway/src/lib/subscription/`).

### 40+ Feature Gates (Rust)

| Categoría | Feature | Tier Mínimo | Add-On Disponible |
|-----------|---------|-------------|-------------------|
| **Core Pipeline** | basic_pipeline | Starter | — |
| | full_pipeline | Business | — |
| | chat_completions | Starter | — |
| | app_generation | Business | — |
| | automation_generation | Business | — |
| | schema_design | Business | — |
| | thinking_engine | Business | — |
| | reasoning_engine | Business | — |
| | logic_chains | Business | — |
| **MCP Gateway** | mcp_gateway | Enterprise | — |
| | mcp_tools_register | Enterprise | — |
| | mcp_rate_limit_custom | Enterprise | — |
| | mcp_audit_full | Enterprise | — |
| **RBAC** | rbac_basic | Business | — |
| | rbac_full | Enterprise | — |
| | rbac_dangerous_actions | Enterprise | — |
| **Observability** | observability_basic | Business | ✓ ($25/mo) |
| | observability_full | Enterprise | — |
| | observability_export | Enterprise | — |
| **Playbooks** | playbook_library | Business | — |
| | playbook_custom | Enterprise | — |
| | playbook_roi | Business | — |
| **Policy Engine** | policy_engine_basic | Enterprise | ✓ ($30/mo) |
| | policy_engine_full | Enterprise | — |
| | policy_compliance_mapping | Enterprise | — |
| | policy_conflict_detection | Enterprise | — |
| | policy_versioning | Enterprise | — |
| | policy_simulation | Enterprise | — |
| **HITL** | hitl_approvals | Business | ✓ ($35/mo) |
| | hitl_reversible_actions | Enterprise | — |
| | hitl_delegation | Enterprise | — |
| | hitl_escalation | Enterprise | — |
| | hitl_evidence | Enterprise | — |
| | hitl_sla_tracking | Enterprise | — |
| **Executors** | executor_basic | Starter | — |
| | executor_advanced | Business | — |
| | executor_all | Enterprise | — |
| **Merkle Audit** | merkle_audit | Enterprise | — |
| **Verdict** | verdict_basic | Starter | — |
| | verdict_consensus | Business | — |
| | verdict_full | Enterprise | — |
| **On-Premise** | self_hosted | On-Premise | — |
| | white_label | On-Premise | — |
| | source_code_access | On-Premise | — |
| | custom_integrations | On-Premise | — |
| | air_gap | On-Premise | — |
| | military_encryption | On-Premise | — |
| **API Rate** | api_rate_30 | Starter | — |
| | api_rate_100 | Business | — |
| | api_rate_1000 | Enterprise | — |
| | api_rate_unlimited | On-Premise | — |
| **Support** | community_support | Starter | — |
| | priority_support | Business | — |
| | dedicated_support | Enterprise | — |
| | dedicated_engineer | On-Premise | — |
| **SLA** | sla_standard (99.5%) | Starter | — |
| | sla_high (99.9%) | Enterprise | — |
| | sla_custom | On-Premise | — |

---

## 10. Workspace Rust — 12 Crates

El workspace Rust `zenic-v2/` contiene 12 crates organizados por dominio:

| # | Crate | Descripción | Archivos Clave | Estado |
|---|-------|-------------|----------------|--------|
| 1 | **zenic-proto** | Tipos protocolo: IDs, dominio, node_types | lib.rs, ids.rs, domain.rs, node_types.rs, serde_.rs | ✅ Producción |
| 2 | **zenic-graph** | DAG Fractal: SuperNode→SubGraph→Node | graph.rs, supernode.rs, subgraph.rs, catalog.rs, descriptor.rs | ✅ Producción |
| 3 | **zenic-runtime** | Ejecución DAG: loader, executor, memory, scheduler | executor.rs, loader.rs, memory.rs, context.rs, scheduler.rs | ✅ Producción |
| 4 | **zenic-flow** | Motor de workflows: steps, checkpoints, retry | engine.rs, step.rs, checkpoint.rs, retry.rs, compensation.rs | ✅ Producción |
| 5 | **zenic-policy** | Motor de políticas: rules, gates, roles, audit | engine.rs, rule.rs, gate.rs, role.rs, permission.rs, audit.rs | ✅ Producción |
| 6 | **zenic-safety** | Safety Gate: categories, sensitivity, verdicts | engine.rs, categories.rs, sensitivity.rs, verdict.rs, domain_rules.rs, compliance.rs | ✅ Producción |
| 7 | **zenic-core** | Orquestador principal | orchestrator.rs, config.rs, session.rs, router.rs, step_bridge.rs | ✅ Producción |
| 8 | **zenic-memory** | Chip de Memoria Adaptativa Binaria | 16 archivos (ver sección 3) | ✅ Producción |
| 9 | **zenic-subscription** | Suscripción SaaS: tiers, pricing, SAGA | types.rs, pricing.rs, engine.rs, feature_gates.rs, saga/ (6 flujos) | ✅ Producción |
| 10 | **zenic-pybridge** | Puente PyO3 → `_zenic_native` | 22+ módulos Rust expuestos a Python | ✅ Producción |
| 11 | **zenic-bench** | Benchmarks de rendimiento | lib.rs (stub) | ⏳ Stub |
| 12 | **zenic-tests** | Tests de integración | lib.rs (stub) | ⏳ Stub |
| 13 | **zenic-ffi** | Interfaz FFI C | lib.rs (stub) | ⏳ Stub |

### Dependencias Compartidas (Workspace)

```toml
serde = "1.0"
bincode = "1.3"
zstd = "0.13"
thiserror = "2.0"
uuid = "1.11"
petgraph = "0.7"
indexmap = "2.7"
tracing = "0.1"
```

---

## 11. PyO3 Bridge — Módulo \_zenic\_native

El crate `zenic-pybridge` expone 18+ módulos Rust nativos a Python a través de PyO3/maturin. El módulo Python resultante es `_zenic_native` (v2.5.0).

### Módulos Expuestos

| Módulo | Funcionalidad | Componentes Clave |
|--------|---------------|-------------------|
| **crypto** | Criptografía | PBKDF2, Argon2id, constant-time compare |
| **hash** | Hashing | BLAKE3, xxHash64, Merkle root |
| **db** | Base de datos cifrada | SQLCipher (EncryptedDb class) |
| **forensic** | Análisis forense | Merkle chain verification, proof generation |
| **rollback** | Rollback atómico | File snapshot/restore, atomic rollback |
| **eventbus** | Bus de eventos | Wildcard matching, route resolution, dedup |
| **simulation** | Simulación DAG | Topological sort, cycle detection, dry-run |
| **risk** | Motor de riesgo | Blast radius, risk propagation, critical path |
| **bus** | Memoria compartida | SharedMemoryBus, SharedState, RingBuffer |
| **safety_gate** | Safety Gate Rust | ActionCategory, SafetyVerdict, validate/classify/rate_limit |
| **license** | Licenciamiento | LicenseTier, LicenseStatus, verify_license, kill switch |
| **memory_chip** | Chip de Memoria | MemoryEngine, DagAdapter, SubscriptionGate |
| **e2e_pipeline** | Pipeline E2E | Flujo completo de 9 pasos |
| **catalog** | Catálogo de nichos | 24 nichos industriales |
| **certifier** | Certificador | Firma ECDSA de blueprints |
| **completer** | Auto-completado | Sugerencias contextuales |
| **extractor** | Extracción | Parser de documentos |
| **ingest** | Ingesta | Procesamiento de datos entrantes |
| **niche** | Nichos | Reglas de dominio por nicho |
| **template** | Templates | Sistema de plantillas DNA |

### Fallback Python

Cada módulo Rust tiene un fallback en Python (`src/core/native/_fallbacks.py`) que se activa si la extensión nativa no está compilada. Esto garantiza compatibilidad total.

---

## 12. Codebase Python — 30+ Subsistemas

### Estructura `src/core/`

| Módulo | Propósito | Componentes |
|--------|-----------|-------------|
| **orchestrator_base** | Pipeline de 8 niveles | `_init_mixin`, `_api_mixin`, `_phase7_mixin`, `_phase8_mixin`, `_compat_mixin` |
| **verdict_parts** | Motor de veredicto 4 capas | `deterministic_pipeline/` (9 tareas), `verdict_engine/`, `consensus_resolver`, `evidence_collector` |
| **conversational** | IA conversacional multi-turno | `conversation_engine`, `session_manager`, `llm_translator`, `llm_drafter`, `memory/`, `routing/`, `tools/` |
| **executors** | 19 ejecutores de acciones | database, email, file, dry_run, simulation, safety_gate, policy_engine, audit_logger, etc. |
| **agents/** | Agentes especializados | `understanding/`, `validation/`, `reasoning/`, `verdict/`, `automation/`, `business/`, `infrastructure/`, `memory/` |
| **approval** | Cadenas HITL | chain, workflows, evidence, delegation, escalation, rollback, adaptive, risk_routing, justification, batch, audit_merkle |
| **defense** | 6 capas de defensa | anti_tampering, binary_hardening, encryption, integrity, server_secrets |
| **blueprints** | Sistema de blueprints | schema, loader, composer, validator, certifier, converter, sdk, onboarding, boot, partner_registry |
| **sna** | Sistema Nervioso Autónomo | sna_engine, scheduler, alert_manager, thresholds, persistence, dag_integration |
| **distributed** | Computación distribuida | saga_coordinator/, leader_election, worker/, task_queue/, lock_manager/, circuit_breaker_distributed/ |
| **shared** | Utilidades compartidas | types, constants, contracts, resource_governor, constraint_solver, z3_solver, mcts |
| **memory_parts** | Subsistema de memoria | database, longterm, cache, episodes, memory/(_core, _session_mixin, _tenant_mixin) |
| **learning** | Motor de aprendizaje | learning_engine, outcome_tracker |
| **license** | Licencias ECDSA | signer, manager, types, persistence, hw_binding |
| **degraded_mode** | Modo degradado | manager, types, persistence, capabilities |
| **model_mgr_parts** | Gestor de modelo | singleton, monitor, ram_mgmt, unload, status, ai_access, semantic_access |
| **mini_ai_parts** | Mini IA (Qwen3-0.6B) | _engine, _fallbacks, _lifecycle, _tasks/, _verdict_mixin/ |
| **code_gen_parts** | Generación de código | assembler/, smart_chain/, _pipeline_mixin/, _contextual_mixin/ |
| **dna_loader_parts** | Carga de DNA | _loader, _loaders_mixin, _glossary_mixin, _logic_modules_mixin |
| **reasoning_parts** | Motor de razonamiento | _engine, _step_mixin, _helpers_mixin, _reflect_mixin, _context_mixin |
| **semantic_parts** | Motor semántico | engine, _mixin_embed, _mixin_classify, _mixin_search, _mixin_lifecycle |
| **thinking_parts** | Motor de pensamiento | _reasoning_mixin, _planning_mixin, _context_mixin |
| **patterns** | 18 patrones de diseño | creational/, structural/, behavioral/, architectural/, orchestration/, resilience/, concurrency/ |
| **niche_rust** | Bridge Rust para nichos | bridge, certifier_bridge, e2e_bridge, ingest_bridge, document_parser |
| **plugins** | Sistema de plugins | registry, lifecycle, hook_system, types |
| **channels** | Notificaciones multi-canal | providers/(whatsapp, email, slack, teams, push, twilio_sms) |
| **autopilot** | Sistema Autopilot | engine, planner, feedback, objective, kpi_tracker, autonomy |
| **roi** | Tracking ROI | value_tracker, cost_accumulator, dashboard_data, impact_scorer |
| **observability** | Stack de observabilidad | metrics/, tracing/, audit/, forensic, health, snapshot_audit |
| **chaos** | Chaos engineering | experiment_runner, steady_state, types |
| **risk** | Motor de riesgo | engine, types |
| **policy_code** | Policy DSL | engine, builtins, types |
| **knowledge** | Knowledge Graph | graph_engine, cross_agent, types |
| **events** | Sistema de eventos | schema_registry, replay_queue, trigger_map |
| **exceptions** | Taxonomía de excepciones | taxonomy, routing, engine, analytics |
| **workflows** | Cadenas de workflows | chain_composer, chain_templates, conditional_branch, inter_workflow |
| **logic_blocks** | Builder de bloques lógicos | flow, builder, builder_registry, validation, auth, data, chain, business_logic |

### DNA Templates (`src/config/templates/dna/`)

| Template | Propósito |
|----------|-----------|
| `validation_gates.yaml` | Puertas de validación por dominio |
| `domain_expert_rules.yaml` | Reglas de experto por dominio |
| `logic_modules.yaml` | Módulos lógicos configurables |
| `professional_glossary.yaml` | Glosario profesional |

---

## 13. Gateway TypeScript — Next.js 16 + Prisma

El Gateway es una aplicación Next.js 16 con TypeScript que expone 80+ API routes y actúa como interfaz web del sistema.

### Stack

| Tecnología | Versión |
|------------|---------|
| Next.js | 16.2.6 |
| TypeScript | 6.0.3 |
| Prisma | 5.22.0 |

### Subsistemas TypeScript

| Módulo | Propósito | Archivos |
|--------|-----------|----------|
| **policy-engine** | Motor de políticas TS | evaluator, hot-reload, templates, simulator, composition, namespaces, approval, conflict-detector, constraint-solver, impact, compliance-map, versioning, diff, yaml-loader, testing, types |
| **hitl** | Human-in-the-loop TS | approval-engine, pipeline-integration, reversible-action, sla-service, expiry-service, notifications, approval-audit, delegation, justification-service, evidence-service, hitl-coordinator, types |
| **observability** | Observabilidad TS | metrics/(collector, business, security, resilience), tracing/(collector, span-builder), export/(json, otel), types |
| **playbooks** | Playbooks TS | engine, metrics-collector, yaml-loader, roi-calculator, pricing-engine, onboarding-wizard, compliance-map, certification, types |
| **mcp-gateway** | Gateway MCP | protocol/(parser, types), auth/, audit/, engine/, adapters/(native, openai), services/, rate-limiter/, sdk/ |
| **subscription** | Suscripción TS | types.ts (524 líneas), feature-gate-middleware.ts, route-guards.ts, guard-handler.ts, index.ts |

---

## 14. Serialización — rkyv + bincode + serde\_json

Estrategia de serialización de 3 capas según el contexto de uso:

| Formato | Uso | Rendimiento | Zero-copy | Tamaño |
|---------|-----|-------------|-----------|--------|
| **rkyv** | Tránsito (SharedMemoryBus, DAG context, Policy hot path) | Máximo | ✓ | Compacto |
| **bincode** | Persistencia (MerkleLedger, SQLCipher storage) | Alto | ✗ | Muy compacto |
| **serde_json** | APIs externas únicamente | Bajo | ✗ | Grande |

### NodeValue — Reemplazo de serde\_json::Value en Hot Paths

```rust
pub enum NodeValue {
    Null, Bool(bool), I64(i64), U64(u64), F64(f64),
    Text(String), Binary(Vec<u8>), Array(Vec<NodeValue>),
    Map(Vec<(String, NodeValue)>),
}
```

- Conversión bidireccional con `serde_json::Value` en fronteras de API
- Compatible con rkyv para zero-copy en SharedMemoryBus
- Compatible con bincode para persistencia compacta

---

## 15. MerkleLedger — Auditoría Inmutable BLAKE3

Cada acción ejecutada queda registrada en un **Merkle Ledger** con hash chains BLAKE3:

- Cada entrada incluye hash de la entrada anterior → cadena inmutable
- Pruebas de inclusión generables (Merkle proof)
- Verificación en batch (batch verify)
- Almacenamiento en bincode (compacto) con SQLCipher (cifrado)

### Módulo Forense (Rust → Python)

- `merkle_chain_verification` — Verifica integridad de la cadena completa
- `proof_generation` — Genera prueba Merkle para una entrada específica
- `batch_verify` — Verifica múltiples entradas en batch

---

## 16. Safety Gate — Doble Capa Inbypassable

### Capa 1: SafetyGate (Python)

- Clasifica acciones: `SAFE` / `DESTRUCTIVE` / `FINANCIAL`
- Rate limiting: 30 acciones/minuto por tipo, 200/hora por categoría, 10 destructivas/hora, 20 financieras/hora
- Thread-safe

### Capa 2: DomainSafetyGate (Rust, 4 sub-capas)

1. **10 reglas base** — Clasificación universal de acciones
2. **35 reglas de dominio** — Específicas por nicho industrial
3. **8 DENY absolutos** — Acciones que NUNCA se pueden ejecutar:
   - Transferencias no autorizadas
   - Modificar recetas médicas
   - Bypass de compliance
   - Borrar documentos legales
   - Escalar privilegios sin autorización
   - Modificar logs de auditoría
   - Acceder a datos de otros tenants
   - Ejecutar código arbitrario en producción
4. **8 estándares compliance** — HIPAA, PCI-DSS, GDPR, SOX, AML/KYC, COPPA, ISO 27001, SOC 2

### Invariante Arquitectónico

- **DENY es inmutable**: El campo `verdict` es privado con solo getters. No existe `set_verdict`. No existe mutación.
- **Las reglas solo escalan**: `ALLOW → CONFIRM → APPROVE → DENY`. Nunca al revés. El compilador Rust lo garantiza.
- **Si la base dice DENY, el domain gate NO puede sobreescribir**.

---

## 17. 19 Ejecutores de Acciones

| # | Ejecutor | Descripción | Tier Mínimo |
|---|----------|-------------|-------------|
| 1 | **database** | Operaciones de base de datos | Business |
| 2 | **email** | Envío de correos | Starter |
| 3 | **file** | Operaciones de archivos | Starter |
| 4 | **http** | Requests HTTP | Starter |
| 5 | **dry_run** | Simulación sin ejecución | Enterprise |
| 6 | **simulation** | Simulación de escenarios | Enterprise |
| 7 | **safety_gate** | Verificación de seguridad | Starter |
| 8 | **policy_engine** | Evaluación de políticas | Business |
| 9 | **audit_logger** | Registro de auditoría | Starter |
| 10 | **impact_preview** | Vista previa de impacto | Business |
| 11 | **diff_preview** | Vista previa de cambios | Business |
| 12 | **transform** | Transformación de datos | Business |
| 13 | **schedule** | Programación de tareas | Business |
| 14 | **coordinated_rollback** | Rollback coordinado | Enterprise |
| 15 | **blueprint_schema** | Schema de blueprints | Business |
| 16 | **jira** | Integración Jira | Business |
| 17 | **servicenow** | Integración ServiceNow | Business |
| 18 | **dispatch_action** | Despacho de acciones | Starter |
| 19 | **base** | Ejecutor base (abstracto) | Starter |

Todos los ejecutores son auditados en el Merkle Ledger.

---

## 18. 24 Nichos Industriales

Cada nicho tiene compliance integrado y reglas de dominio específicas:

| # | Nicho | Compliance | DENY Absolutos |
|---|-------|-----------|----------------|
| 1 | Telemedicina | HIPAA | Modificar recetas médicas |
| 2 | FinTech / Banca | PCI-DSS, AML/KYC | Transferencias no autorizadas |
| 3 | EdTech | COPPA, FERPA | Filtrado de contenido menor |
| 4 | LegalTech | SOX, eIDAS | Borrar documentos legales |
| 5 | PropTech | GDPR, SOX | Acceso no autorizado a datos |
| 6 | InsurTech | GDPR, SOX | Modificar pólizas sin aprobación |
| 7 | Supply Chain | ISO 27001 | Bypass de trazabilidad |
| 8 | Manufacturing | ISO 27001 | Modificar parámetros de seguridad |
| 9 | Retail / E-Commerce | PCI-DSS, GDPR | Procesar pagos sin cifrar |
| 10 | AgriTech | GDPR | Borrar datos de cultivos |
| 11 | Energy | NERC CIP | Apagar sistemas críticos |
| 12 | Government | FISMA, SOC 2 | Acceso no autorizado a datos |
| 13 | HR / HCM | GDPR, SOC 2 | Acceder a datos de empleados sin autorización |
| 14 | Logistics | ISO 28000 | Modificar rutas de envío crítico |
| 15 | Hospitality | PCI-DSS | Procesar pagos sin compliance |
| 16 | Media / Entertainment | DMCA, GDPR | Distribuir contenido protegido |
| 17 | Telecom | GDPR, SOX | Modificar contratos de servicio |
| 18 | Construction | ISO 45001 | Ignorar alertas de seguridad |
| 19 | Automotive | ISO 26262 | Modificar parámetros de seguridad vehicular |
| 20 | Pharma | FDA 21 CFR Part 11 | Modificar datos de ensayos clínicos |
| 21 | Aviation | DO-178C | Bypass de verificación de seguridad |
| 22 | Maritime | ISM Code | Ignorar procedimientos de emergencia |
| 23 | Mining | ISO 45001 | Desactivar monitores de gas |
| 24 | Proptech / Gemelos Digitales | BREEAM/LEED | Modificar datos de sensores |

---

## 19. Defensa en 6 Capas

| Capa | Componente | Scoring | Consecuencia de Manipulación |
|------|-----------|---------|------------------------------|
| 1 | **Anti-tampering** | 0-100 | Si detecta manipulación → modo degradado |
| 2 | **Binary hardening** | 0-100 | Verificación de integridad del binario |
| 3 | **Encryption** | 0-100 | Cifrado de datos en reposo y tránsito |
| 4 | **Integrity** | 0-100 | Verificación de integridad de archivos |
| 5 | **Licenses** | 0-100 | Verificación de licencia ECDSA |
| 6 | **Server secrets** | 0-100 | Protección de secrets del servidor |

### Modo Degradado

Si el sistema detecta manipulación, entra en **modo degradado** (parálisis selectiva):
- Solo permite operaciones de solo lectura
- Bloquea todas las operaciones destructivas y financieras
- Requiere intervención administrativa para restaurar

---

## 20. Sistema Nervioso Autónomo (SNA)

13 monitores proactivos que operan sin intervención del usuario:

| Monitor | Tipo | Descripción |
|---------|------|-------------|
| Lightweight | Ligero | CPU, memoria, disco, red |
| Medium | Medio | Latencia de API, throughput, errores |
| Heavy | Pesado | Integrity checks, compliance drift, security posture |

### Componentes SNA

- `sna_engine` — Motor principal
- `scheduler` — Programación de monitores
- `alert_manager` — Gestión de alertas
- `thresholds` — Umbrales configurables
- `persistence` — Persistencia de estado
- `dag_integration` — Integración con DAG

---

## 21. Sistema Distribuido

| Componente | Implementación |
|------------|---------------|
| **SAGA Coordinator** | Coordinación transaccional distribuida |
| **Leader Election** | Elección de líder entre nodos |
| **Worker Pool** | Pool de workers con work-stealing |
| **Task Queue** | Cola de tareas distribuida |
| **Lock Manager** | Gestión de locks distribuidos |
| **Circuit Breaker** | Circuit breaker distribuido |
| **Backend** | PostgreSQL + Memory backends |
| **Topology** | Gestión de topología de nodos |

---

## 22. Blueprints Certificados

Flujo de certificación:

```
YAML Template → Validación → Safety Gate → Firma ECDSA → Blueprint Certificado
```

### Componentes

- `schema` — Schema de definición de blueprints
- `loader` — Carga de blueprints desde archivos
- `composer` — Composición de blueprints complejos
- `validator` — Validación contra schema
- `certifier` — Certificación con firma ECDSA
- `converter` — Conversión entre formatos
- `sdk` — SDK para desarrollo de blueprints
- `onboarding` — Onboarding guiado
- `boot` — Bootstrapping de blueprints
- `partner_registry` — Registro de partners
- `registry` — Registry global de blueprints

---

## 23. Yamil — Agente Creador de Plantillas

Del nicho al blueprint certificado en un flujo unificado. 57 tests dedicados.

- Transforma especificaciones de nicho en blueprints certificados
- Genera templates YAML, validación gates, y reglas de dominio
- Integra con el sistema de certificación ECDSA

---

## 24. Patrones de Diseño (18 Módulos)

| Categoría | Patrones |
|-----------|----------|
| **Creational** | Factory, Abstract Factory, Builder, Singleton, Prototype |
| **Structural** | Adapter, Bridge, Composite, Decorator, Facade, Proxy |
| **Behavioral** | Chain of Responsibility, Command, Strategy, Observer, State |
| **Architectural** | MVC, Clean Architecture, Hexagonal, CQRS |
| **Orchestration** | Saga, Choreography, Pipeline |
| **Resilience** | Circuit Breaker, Retry, Bulkhead, Timeout |
| **Concurrency** | Actor, Thread Pool, Future/Promise, CSP |

---

## 25. Motor Conversacional

Sistema de IA conversacional multi-turno con los siguientes componentes:

| Componente | Descripción |
|------------|-------------|
| `conversation_engine` | Motor de conversación |
| `session_manager` | Gestión de sesiones |
| `zenic_bridge` | Puente con el orquestador |
| `llm_translator` | Traducción de intenciones a acciones |
| `llm_drafter` | Generación de borradores (limitada) |
| `memory/` | Memoria conversacional |
| `routing/` | Enrutamiento de intenciones |
| `tools/` | Herramientas disponibles |
| `personality_manager` | Gestión de personalidad |

---

## 26. Sistema de Plugins

| Componente | Descripción |
|------------|-------------|
| `registry` | Registro de plugins |
| `lifecycle` | Ciclo de vida (load, enable, disable, unload) |
| `hook_system` | Sistema de hooks (before, after, around) |
| `types` | Tipos y contratos |

---

## 27. Canales de Notificación

| Proveedor | Protocolo |
|-----------|-----------|
| WhatsApp | API de WhatsApp Business |
| Email | SMTP |
| Slack | Webhook API |
| Microsoft Teams | Webhook API |
| Push | FCM/APNs |
| SMS (Twilio) | Twilio API |

---

## 28. Autopilot y ROI

### Autopilot

| Componente | Descripción |
|------------|-------------|
| `engine` | Motor de piloto automático |
| `planner` | Planificación de objetivos |
| `feedback` | Sistema de retroalimentación |
| `objective` | Definición de objetivos |
| `kpi_tracker` | Tracking de KPIs |
| `autonomy` | Niveles de autonomía |

### ROI

| Componente | Descripción |
|------------|-------------|
| `value_tracker` | Tracking de valor generado |
| `cost_accumulator` | Acumulación de costos |
| `dashboard_data` | Datos para dashboard |
| `impact_scorer` | Scoring de impacto |

---

## 29. Observabilidad

### Stack Completo

| Componente | Métricas | Traces | Export |
|------------|---------|--------|--------|
| **Collector** | ✓ Business, Security, Resilience | ✓ Span Builder | ✓ JSON, OpenTelemetry |
| **Audit** | ✓ | ✓ | ✓ |
| **Forensic** | ✓ Merkle verification | ✓ | ✓ |
| **Health** | ✓ | ✓ | ✓ |
| **Snapshot Audit** | ✓ | ✓ | ✓ |

---

## 30. Playbooks

| Componente | Descripción |
|------------|-------------|
| `engine` | Motor de ejecución |
| `metrics-collector` | Recopilación de métricas |
| `yaml-loader` | Carga desde YAML |
| `roi-calculator` | Cálculo de ROI |
| `pricing-engine` | Motor de precios |
| `onboarding-wizard` | Asistente de onboarding |
| `compliance-map` | Mapa de compliance |
| `certification` | Certificación de playbooks |

---

## 31. Policy Engine (DSL)

Motor de políticas con DSL propio:

| Componente | Descripción |
|------------|-------------|
| `engine` | Motor de evaluación |
| `builtins` | Funciones built-in |
| `types` | Tipos y contratos |

### Conflict Detection

- **Z3 Solver** — Resolución de restricciones lógicas
- **AC-3 Solver** — Propagación de restricciones
- Detección automática de conflictos entre reglas

---

## 32. Caos Engineering

| Componente | Descripción |
|------------|-------------|
| `experiment_runner` | Ejecutor de experimentos |
| `steady_state` | Definición de estado estable |
| `types` | Tipos de experimentos |

---

## 33. Infraestructura de Tests

### Rust

| Componente | Ubicación | Cantidad |
|------------|-----------|----------|
| Workspace tests | `zenic-v2/zenic-*/src/` (inline `#[cfg(test)]`) | 408+ |

### Python

| Categoría | Ubicación | Archivos |
|-----------|-----------|----------|
| Unitarios | `tests/unit/` | 77+ archivos |
| E2E | `tests/e2e/` | 4 suites |
| Integración | `tests/integration/` | test_pipeline.py |
| Phase D | `tests/phase_d/` | Integración |

### Directorios de Tests Python (28+)

test_auth_svc_parts, test_auto_eng_parts, test_action_exec_parts, test_ctx_ptr_parts, test_dna_parts, test_governor_parts, test_low_power_parts, test_mini_ai_parts, test_niche_parts, test_orch_base_parts, test_partial_parts, test_phase7_parts, test_phase8_parts, test_reasoning_parts, test_resp_build_parts, test_semantic_parts, test_shared_types_parts, test_smart_mem_parts, test_step_disp_parts, test_symbolic_parts, test_thinking_parts, test_z3_parts, test_layer5_validation, test_layer6_automation, test_layer7_reasoning, test_layer8_verdict, test_layer9_infrastructure, test_yamil (57 tests)

---

## 34. Stack Tecnológico Completo

| Capa | Tecnología | Versión |
|------|-----------|---------|
| **Backend Python** | Python + FastAPI + Uvicorn | 3.10+ |
| **Motor Nativo** | Rust (PyO3/maturin) | 1.85+ |
| **Gateway Web** | Next.js + TypeScript + Prisma | 16.2.6 |
| **IA** | Qwen3-0.6B (CPU-only, local) | — |
| **Base de datos** | SQLite/SQLCipher (dev), PostgreSQL (prod) | — |
| **Hashing** | BLAKE3, xxHash64 | — |
| **Criptografía** | ECDSA, PBKDF2, Argon2id, Fernet | — |
| **Serialización** | rkyv (tránsito), bincode (persistencia), serde_json (APIs) | — |
| **Pagos** | USDT TRC20 exclusivamente | — |
| **Plataformas** | x86_64, ARM64 (Android/Termux) | — |
| **Memoria mínima** | 500MB RAM | — |

---

## 35. Estructura de Directorios

```
Zenic-Agents/
├── README.md                    # Documentación principal
├── README-1.md                  # ★ Documentación técnica completa (este archivo)
├── pyproject.toml               # Configuración Python (maturin)
├── requirements.txt             # Dependencias pip
├── native/                      # Legacy native/src/lib.rs (obsoleto → zenic-v2/)
├── zenic-v2/                    # ★ Workspace Rust (12 crates)
│   ├── Cargo.toml               # Workspace config
│   ├── zenic-proto/             # Tipos protocolo
│   ├── zenic-graph/             # DAG Fractal
│   ├── zenic-runtime/           # Ejecución DAG
│   ├── zenic-flow/              # Motor de workflows
│   ├── zenic-policy/            # Motor de políticas
│   ├── zenic-safety/            # Safety Gate
│   ├── zenic-core/              # Orquestador
│   ├── zenic-memory/            # ★ Chip de Memoria Adaptativa Binaria
│   ├── zenic-subscription/      # ★ Suscripción SaaS
│   ├── zenic-pybridge/          # ★ Puente PyO3
│   ├── zenic-bench/             # Benchmarks (stub)
│   ├── zenic-tests/             # Tests integración (stub)
│   └── zenic-ffi/               # FFI C (stub)
├── src/                         # ★ Codebase Python
│   ├── __init__.py
│   ├── entrypoints/             # 3 entry points
│   │   ├── main.py              # TUI interactiva
│   │   ├── main_conversational.py  # Modo conversacional
│   │   └── main_headless.py     # CLI headless
│   ├── config/                  # Configuración
│   │   ├── loader.py
│   │   └── settings.yaml
│   ├── templates/dna/           # Templates YAML
│   └── core/                    # ★ Motor principal (30+ subsistemas)
├── gateway/                     # ★ Gateway TypeScript (Next.js 16)
│   ├── package.json
│   ├── src/
│   │   ├── app/api/            # 80+ API routes
│   │   └── lib/                # Librerías (subscription, policy-engine, etc.)
│   ├── policy-engine/          # Motor de políticas TS
│   ├── hitl/                   # HITL TS
│   ├── observability/          # Observabilidad TS
│   ├── playbooks/              # Playbooks TS
│   └── mcp-gateway/            # MCP Gateway TS
├── docs/                        # Documentación de arquitectura
│   └── architecture/
│       ├── PLAN-DEFINITIVO-V3-FINAL.md   # ★ Plan aprobado 47/47
│       ├── CHIP-MEMORIA-ADAPTATIVA-BINARIA.md
│       ├── FLUJO-APRENDIZAJE-4-CAPAS-VEREDICTO.md
│       └── SERIALIZACION-RKYV-BINCODE.md
├── tests/                       # Tests Python
│   ├── unit/                    # 77+ archivos
│   ├── e2e/                     # 4 suites
│   ├── integration/             # Integración
│   └── phase_d/                 # Phase D
└── scripts/                     # Scripts de utilidad
    ├── install_termux.sh        # Instalación Android/Termux
    └── fix_cline_connection.sh  # Fix conexión Cline
```

---

## 36. Mapa Completo de Features por Nivel de Suscripción

### Starter ($29/mo)

| Feature | Disponible |
|---------|-----------|
| Pipeline básico (L1-L4 parcial) | ✓ |
| Chat completions API | ✓ |
| Ejecutores básicos (file, shell, http) | ✓ |
| Veredicto determinístico | ✓ |
| Schema Drift (memory chip) | ✓ |
| 10 mappings/mes, LRU 100 | ✓ |
| 5 workflows | ✓ |
| 100 acciones/día | ✓ |
| 3 team members | ✓ |
| 30 API calls/min | ✓ |
| Community support | ✓ |
| Email notifications | ✓ |
| SLA estándar (99.5%) | ✓ |

### Business ($99/mo)

Todo lo de Starter **más**:

| Feature | Disponible |
|---------|-----------|
| Pipeline completo (L1-L8) | ✓ |
| App generation | ✓ |
| Automation generation | ✓ |
| Schema design | ✓ |
| Thinking engine | ✓ |
| Reasoning engine | ✓ |
| Logic chains | ✓ |
| Evidence Collector + Consensus Resolver | ✓ |
| Intent Routing (memory chip) | ✓ |
| 50 mappings/mes, LRU 500 | ✓ |
| DAG Node Adapt (paso 5) | ✓ |
| Pasos 6-8 del pipeline | ✓ |
| Ejecutores avanzados (db, api, transform) | ✓ |
| RBAC básico (3 roles) | ✓ |
| Playbook library | ✓ |
| ROI calculation | ✓ |
| 25 workflows | ✓ |
| 1,000 acciones/día | ✓ |
| 15 team members | ✓ |
| 100 API calls/min | ✓ |
| Priority support | ✓ |
| Policy Engine (add-on $30/mo) | Opcional |
| HITL Approvals (add-on $35/mo) | Opcional |
| Advanced Analytics (add-on $25/mo) | Opcional |

### Enterprise ($299/mo)

Todo lo de Business **más**:

| Feature | Disponible |
|---------|-----------|
| Pipeline ilimitado | ✓ |
| 3 mecanismos + Ontología (memory chip) | ✓ |
| Mappings ilimitados, LRU 2,000 | ✓ |
| Simulate dry-run (paso 9) | ✓ |
| MCP Gateway | ✓ |
| RBAC completo (18 permisos, roles custom) | ✓ |
| Observabilidad completa + export | ✓ |
| Policy Engine completo | ✓ |
| HITL completo (delegación, escalamiento, SLA) | ✓ |
| Custom playbooks | ✓ |
| Merkle audit | ✓ |
| Todos los ejecutores (19) | ✓ |
| Compliance mapping (30+ estándares) | ✓ |
| Conflict detection (Z3+AC-3) | ✓ |
| Policy versioning y rollback | ✓ |
| Policy simulation | ✓ |
| Workflows ilimitados | ✓ |
| Acciones ilimitadas | ✓ |
| Team members ilimitados | ✓ |
| 1,000 API calls/min | ✓ |
| SLA alto (99.9%) | ✓ |
| Dedicated support | ✓ |

### On-Premise Enterprise ($799/mo + $2,000 setup)

Todo lo de Enterprise **más**:

| Feature | Disponible |
|---------|-----------|
| Self-hosted deployment | ✓ |
| White-label branding | ✓ |
| Source code access | ✓ |
| Custom integrations | ✓ |
| Air-gap capable | ✓ |
| Military-grade encryption | ✓ |
| Export/Import (memory chip) | ✓ |
| Custom ontology | ✓ |
| Mappings ilimitados, LRU ilimitado | ✓ |
| API calls ilimitados | ✓ |
| Custom SLA | ✓ |
| Dedicated on-site engineer | ✓ |
| Data sovereignty | ✓ |
| Custom deployment | ✓ |

---

## 37. 3 Grietas Reparadas

### Grieta 1: ¿Cómo modifica el Chip el DAG?

**Problema**: No estaba definido cómo el Chip de Memoria interactuaba con la ejecución del DAG.

**Solución**: `dag_adapter.rs` — Middleware de intercepción
- Topología del DAG es INMUTABLE (no se agregan/eliminan nodos)
- Parámetros son FLEXIBLES (el adapter inyecta parámetros corregidos)
- Si un nodo falla → pausa → consulta memoria → inyecta → re-ejecuta

### Grieta 2: 7 tareas sin mapear

**Problema**: El pipeline tenía 7 tareas pero no estaban conectadas al Chip de Memoria.

**Solución**: Expansión a 9 tareas
- Agregado `memory_lookup` en paso 1 (búsqueda en Knowledge Graph)
- Agregado `dag_node_adapt` en paso 5 (adaptación de nodo DAG con memoria)

### Grieta 3: Justificación de admin no explícita

**Problema**: HITL no tenía campos obligatorios para justificación de aprobación.

**Solución**: 3 campos obligatorios tipados
- `admin_evidence_review: bool` (debe ser `true`)
- `admin_justification: String` (mínimo 50 caracteres, no "ok")
- `risk_acknowledgment: bool + admin_session_id` (ambos obligatorios, crypto-linked)
- La compilación YAML FALLA si no se completan

---

## 38. Plan de Implementación — 5 Fases

### Fase 1: Foundation — zenic-memory + rkyv infra ✅

- Crate `zenic-memory` con tipos core
- Integración rkyv en SharedMemoryBus
- Tablas SQLite (semantic_mappings, ontology_base, learning_audit)
- FeatureGate por tier para memory

### Fase 2: 3 Mecanismos + rkyv hot path ✅

- Schema Drift detector
- Intent Routing engine
- Policy Refinement classifier
- rkyv en hot paths (SharedMemoryBus, DAG context, Policy eval)

### Fase 3: Verdict Pipeline integration + PyO3 bridge

- 9-step DeterministicPipeline en Python
- VerdictAdapter en Rust
- PyO3 bridge (memory_chip module)
- HITL bridge Python ↔ Rust

### Fase 4: HITL strict + Merkle + YAML

- 3 campos obligatorios en MemoryApprovalRequest
- MerkleSeal para mappings aprobados
- YAML renderer con validación obligatoria
- Fix 3 duplicaciones pendientes

### Fase 5: Subscription gates + API routes + TS↔Rust bridge

- Feature gates en todas las API routes
- Subscription middleware en Gateway
- TS↔Rust bridge para feature checking
- Documentación de API completa

---

## 39. API Routes — 80+ Endpoints

### Subscription API

```
POST   /api/v1/subscription/signup
POST   /api/v1/subscription/cancel
POST   /api/v1/subscription/upgrade
POST   /api/v1/subscription/renew
GET    /api/v1/subscription/check-feature
GET    /api/v1/subscription/tiers
POST   /api/v1/subscription/usage/check
POST   /api/v1/subscription/usage/record
POST   /api/v1/subscription/payment/submit-tx
POST   /api/v1/subscription/payment/confirm
GET    /api/v1/subscription/[tenantId]
```

### Policy Engine API

```
GET    /api/v1/policy-engine/rules
POST   /api/v1/policy-engine/rules
PUT    /api/v1/policy-engine/rules/[id]
DELETE /api/v1/policy-engine/rules/[id]
POST   /api/v1/policy-engine/evaluate
POST   /api/v1/policy-engine/simulate
GET    /api/v1/policy-engine/compliance-map
POST   /api/v1/policy-engine/conflicts
```

### HITL API

```
GET    /api/v1/hitl/approvals
POST   /api/v1/hitl/approvals/[id]/approve
POST   /api/v1/hitl/approvals/[id]/reject
POST   /api/v1/hitl/approvals/[id]/delegate
GET    /api/v1/hitl/escalations
GET    /api/v1/hitl/sla
```

### Observability API

```
GET    /api/v1/observability/metrics
GET    /api/v1/observability/traces
GET    /api/v1/observability/health
GET    /api/v1/observability/export/json
GET    /api/v1/observability/export/otel
```

### Playbooks API

```
GET    /api/v1/playbooks
POST   /api/v1/playbooks
GET    /api/v1/playbooks/[id]
POST   /api/v1/playbooks/[id]/execute
GET    /api/v1/playbooks/roi
```

### MCP Gateway API

```
GET    /api/v1/mcp/tools
POST   /api/v1/mcp/tools/register
POST   /api/v1/mcp/execute
GET    /api/v1/mcp/audit
```

### RBAC API

```
GET    /api/rbac/roles
POST   /api/rbac/roles
GET    /api/rbac/permissions
POST   /api/rbac/assign
```

### Dashboard API

```
GET    /api/dashboard/overview
GET    /api/dashboard/metrics
GET    /api/dashboard/audit
```

---

## 40. Invariantes del Sistema

1. **LLM NEVER generates** — Solo emite boolean verdict (SÍ/NO)
2. **Zero Operational Hallucinations** — Imposibles por arquitectura
3. **DENY is immutable** — No existe override, no existe set_verdict
4. **Rules only escalate** — ALLOW→CONFIRM→APPROVE→DENY, nunca al revés
5. **DAG topology IMMUTABLE** — Solo parámetros son flexibles (via dag_adapter)
6. **Memory NEVER alters LLM weights** — Modifica DAG config + Policy Engine
7. **HITL 3 mandatory fields** — YAML compilation FAILS if incomplete
8. **USDT TRC20 only** — No other payment methods
9. **Offline capable** — Works without internet (Qwen3-0.6B local)
10. **500MB RAM max** — Designed for constrained resources

---

## 41. Restricciones de Plataforma

| Restricción | Valor |
|-------------|-------|
| Modo offline | Sin internet requerido |
| CPU only | Sin GPU requerida |
| Arquitectura | ARM64 (Termux), x86_64 |
| RAM máxima | 500MB |
| Modelo IA | Qwen3-0.6B (local) |
| Plataforma móvil | Android con Termux |
| Conectividad | Opcional (para APIs cloud) |

---

## 42. Instalación y Ejecución

### Requisitos

- Python 3.10+
- Rust 1.85+ (opcional, para extensión nativa)
- 500MB RAM mínimo

### Instalación Rápida

```bash
# 1. Clonar e instalar
git clone https://github.com/yurislay9-ui/Zenic-Agents.git
cd Zenic-Agents && pip install -r requirements.txt

# 2. Compilar extensión Rust (opcional pero recomendado)
cd zenic-v2/zenic-pybridge && maturin develop --release && cd ../..

# 3. Iniciar
uvicorn src.server.fastapi_app:create_app_from_env --host 0.0.0.0 --port 5000 --factory
```

### Modos de Ejecución

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

---

## 43. Variables de Entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `ZENIC_ENV` | `development` | Entorno de ejecución |
| `ZENIC_PORT` | `5000` | Puerto del servidor |
| `ZENIC_DATA_DIR` | `~/.zenic-agents/data` | Directorio de datos |

---

## 44. Comparativa con Frameworks Existentes

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
| Chip de Memoria Adaptativa | **3 mecanismos** | No | No | No |
| DAG Adapter (inmutable) | **Sí** | No | No | No |
| HITL con justificación obligatoria | **Sí** | No | No | No |
| Suscripción USDT TRC20 | **Sí** | No | No | No |
| Feature Gates por tier | **40+** | No | No | No |

---

## 45. Roadmap

### Completado ✅

- [x] Motor Rust (PyO3) — 18+ módulos nativos con fallback Python
- [x] Workspace zenic-v2 — 12 crates (9 producción + 3 stubs)
- [x] Safety Gate doble capa — base + dominio + compliance + sensibilidad
- [x] 24 nichos industriales con compliance integrado
- [x] Arquitectura de Veredicto (4 capas) — IA solo SÍ/NO
- [x] Blueprint certificado con firma ECDSA
- [x] Yamil — Agente creador de plantillas (57 tests)
- [x] E2E Onboarding Pipeline (8 pasos reanudable)
- [x] Defensa en 6 capas con modo degradado
- [x] Sistema Nervioso Autónomo (13 monitores)
- [x] 19 ejecutores de acciones con auditoría Merkle
- [x] Sistema de Suscripción SaaS (USDT TRC20, Saga pattern)
- [x] Feature Gates (40+ Rust, 80+ TypeScript)
- [x] Chip de Memoria Adaptativa Binaria (3 mecanismos)
- [x] DAG Adapter (intercepción de middleware, topología inmutable)
- [x] HITL con 3 campos obligatorios (GRIETA 3)
- [x] Pipeline Determinístico 9 pasos (GRIETA 2)
- [x] Gateway TypeScript (Next.js 16, 80+ API routes)
- [x] Sistema distribuido (PostgreSQL, SAGA, circuit breaker)
- [x] API OpenAI-compatible (drop-in para Cline/Aide/OpenCode)
- [x] 3 Grietas reparadas (DAG interception, 9-step pipeline, HITL mandatory fields)
- [x] Plan Definitivo V3 — 47/47 requisitos aprobados

### En Progreso 🔄

- [ ] Nombres de nichos en español (traducción cross-cutting)
- [ ] Benchmarks de rendimiento (`zenic-bench`)
- [ ] Fase 3: Verdict Pipeline integration + PyO3 bridge
- [ ] Fase 4: HITL strict + Merkle + YAML
- [ ] Fase 5: Subscription gates + API routes + TS↔Rust bridge
- [ ] Fix 3 duplicaciones Phase 4 (types merge, API overlap, ConditionOperator casing)

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

## 46. Licencia

Propietaria. Todos los derechos reservados. El uso requiere licencia válida firmada con ECDSA.

---

<p align="center">
  <strong>Zenic-Agents v3.0.0</strong> — IA enjaulada. Seguridad por diseño. Determinismo garantizado.
</p>
