# ═══════════════════════════════════════════════════════════════════════════
# PLAN DE EJECUCIÓN — Chip Binario + 4 Capas + rkyv/bincode
# Zenic-Agents v3.0.0 — Tareas Concretas con Paralelismo
# ═══════════════════════════════════════════════════════════════════════════
#
# Referencia arquitectónica: docs/architecture/PLAN-DEFINITIVO-V3-FINAL.md
# ═══════════════════════════════════════════════════════════════════════════

---

## DIAGRAMA DE PARALELISMO

```
FASE 1 ──────────────────────────────────────────────────────────────────
  1-a: Crate skeleton + workspace config       ┐
  1-b: Ontología base YAML                     │ PARALELOS
  1-c: rkyv derives en zenic-proto             │
  1-d: NodeValue en zenic-runtime              ┘
         │
  1-e: types.rs + errors.rs (requiere 1-a)     ┐
  1-f: graph.rs + SQLite schema (requiere 1-a) │ PARALELOS (tras 1-a)
  1-g: cache.rs LRU rkyv (requiere 1-a+1-c)    ┘
         │
  1-h: dag_adapter.rs (requiere 1-e+1-f)       ┐
  1-i: ontology.rs (requiere 1-b+1-f)          │ PARALELOS (tras 1-e/1-f)
  1-j: encode_rkyv en zenic-proto (req 1-c)    ┘
         │
         ▼ Verificar: cargo build -p zenic-memory

FASE 2 ──────────────────────────────────────────────────────────────────
  2-a: hypothesis.rs (requiere F1)              ┐
  2-b: schema_drift.rs (requiere 2-a)           │ SECUENCIAL dentro
  2-c: intent_routing.rs (requiere 2-a)         │ del mecanismo,
  2-d: policy_refinement.rs (requiere 2-a)      ┘ pero PARALELO con:
                                                  │
  2-e: Policy Engine rkyv (requiere 1-c)        ┐ PARALELO
  2-f: Safety Engine rkyv (requiere 1-d)        │ con 2-a..2-d
  2-g: Eliminar JSON.stringify (independiente)   ┘
         │
         ▼ Verificar: 3 mecanismos generan hipótesis

FASE 3 ──────────────────────────────────────────────────────────────────
  3-a: verdict_adapter.rs (requiere F1+F2)      ┐
  3-b: PyO3 bridge memory_chip.rs (req F1+F2)   │ PARALELOS
  3-c: _core.py expandido 9 pasos (req F1)      ┘
         │
  3-d: evidence_collector.py (requiere 3-a)     ┐
  3-e: verdict_engine pre-check (req 3-a)       │ PARALELOS
  3-f: consensus_resolver.py (req 3-a)          │ (tras 3-a)
  3-g: SharedMemoryBus rkyv (req 1-c)           ┘
         │
         ▼ Verificar: flujo end-to-end funciona

FASE 4 ──────────────────────────────────────────────────────────────────
  4-a: hitl_bridge.rs 3 campos obligatorios     ┐
  4-b: merkle_seal.rs bincode+BLAKE3            │ PARALELOS
  4-c: yaml_renderer.rs                         ┘
         │
  4-d: lifecycle.rs Saga workflow (req 4-a+b+c) │
  4-e: chain.py integración (req 4-a)           ┐ PARALELOS
  4-f: TheoremCache bincode (independiente)      ┘ (tras 4-d)
         │
         ▼ Verificar: ciclo completo HITL→Merkle→YAML

FASE 5 ──────────────────────────────────────────────────────────────────
  5-a: subscription_gate.rs                     ┐
  5-b: 9 API routes TypeScript                  │ PARALELOS
  5-c: TS↔Rust Policy bridge                    ┘
         │
  5-d: Actualizar zenic-subscription (req 5-a)  │
         │
         ▼ Verificar: feature gates + API + bridge
         │
         ▼ GIT PUSH + TAG v3.1.0
```

---

## TAREAS DETALLADAS

### ═══════════════════════════════════════════
### FASE 1: Fundación
### ═══════════════════════════════════════════

---

#### TAREA 1-a: Crate Skeleton + Workspace Config
**Tipo**: Rust setup
**Archivos nuevos**:
- `zenic-v2/zenic-memory/Cargo.toml`
- `zenic-v2/zenic-memory/src/lib.rs` (stubs: mod declarations)

**Archivos modificados**:
- `zenic-v2/Cargo.toml` — Agregar `zenic-memory` al workspace + `rkyv = "0.8"` a dependencies

**Contenido concreto**:

`zenic-memory/Cargo.toml`:
```toml
[package]
name = "zenic-memory"
version = "0.1.0"
edition = "2021"

[dependencies]
zenic-proto = { path = "../zenic-proto" }
serde = { workspace = true }
serde_json = "1.0"
uuid = { workspace = true }
chrono = { version = "0.4", features = ["serde"] }
thiserror = { workspace = true }
rkyv = { workspace = true }
rusqlite = { version = "0.31", features = ["bundled"] }
```

`zenic-v2/Cargo.toml` agregar:
```toml
[workspace.dependencies]
rkyv = { version = "0.8", features = ["validation", "bytecheck"] }

[workspace.members]
# ... existentes ...
"zenic-memory",
```

**Criterio**: `cargo build -p zenic-memory` compila (con stubs vacíos)

---

#### TAREA 1-b: Ontología Base YAML
**Tipo**: YAML data
**Archivos nuevos**:
- `zenic-v2/zenic-memory/ontology/base-es.yaml`

**Contenido concreto**: ~50 mapeos universales en español:
```yaml
# Ontología Base Zenic — Español (es)
# Mapeos semánticos universales opt-in por tenant
apiVersion: zenic.agents/v1
kind: OntologyBase
metadata:
  language: es
  version: "1.0.0"
  description: Mapeos semánticos universales en español
mappings:
  # Sinónimos comunes de columnas/campos
  - origin: estatus
    relation: synonym_of
    destination: estado
    domain: general
  - origin: cliente
    relation: synonym_of
    destination: usuario
    domain: crm
  - origin: factura
    relation: synonym_of
    destination: cobro
    domain: finanzas
  - origin: factura
    relation: synonym_of
    destination: recibo
    domain: finanzas
  # ... (~50 mapeos totales)
  # Acciones comunes
  - origin: tumba
    relation: routes_to
    destination: cancelar
    domain: general
  - origin: borrar
    relation: synonym_of
    destination: eliminar
    domain: general
  - origin: quitar
    relation: synonym_of
    destination: eliminar
    domain: general
  # ... más mapeos
```

**Criterio**: YAML válido con ≥50 mapeos, 3+ dominios, parseable por Rust serde_yaml

---

#### TAREA 1-c: rkyv Derives en zenic-proto
**Tipo**: Rust modificación
**Archivos modificados**:
- `zenic-v2/zenic-proto/Cargo.toml` — Agregar `rkyv = { workspace = true }`
- `zenic-v2/zenic-proto/src/ids.rs` — Agregar `#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]` a `ExecutionId`, `SessionId`, `TenantId`, `WorkflowId`, `NodeId`, `SubGraphId`
- `zenic-v2/zenic-proto/src/domain.rs` — Agregar derives a `LoadPolicy`, `BusinessDomain`, `NodeCriticality`

**Criterio**: `cargo build -p zenic-proto` compila con rkyv derives

---

#### TAREA 1-d: NodeValue en zenic-runtime
**Tipo**: Rust modificación
**Archivos modificados**:
- `zenic-v2/zenic-runtime/Cargo.toml` — Agregar `rkyv = { workspace = true }`
- `zenic-v2/zenic-runtime/src/context.rs`:
  - Crear `enum NodeValue` (Null, Bool, I64, F64, Str, Bytes, Map, List) con rkyv derives
  - Implementar `From<serde_json::Value> for NodeValue` y viceversa
  - Cambiar `NodeOutput.data: HashMap<String, serde_json::Value>` → `HashMap<String, NodeValue>`
  - Actualizar `NodeOutput::success()`, `NodeOutput::get()`, tests

**Criterio**: `cargo build -p zenic-runtime` compila. Tests existentes pasan.

---

#### TAREA 1-e: types.rs + errors.rs
**Tipo**: Rust nuevo
**Depende de**: 1-a
**Archivos nuevos**:
- `zenic-v2/zenic-memory/src/types.rs`
- `zenic-v2/zenic-memory/src/errors.rs`

**Contenido types.rs** (del plan v3):
- `SemanticMapping` (id, origin, relation, destination, source, tenant_id, confidence, hit_count, approved_by, admin_justification, approved_at, merkle_hash, created_at)
- `MappingRelation` (SynonymOf, EquivalentTo, RoutesTo, ClassifiesAs, Overrides)
- `MappingSource` (SchemaDrift, IntentRouting, PolicyRefinement, OntologyBase, ManualEntry)
- `LearningVerdict` (mapping, hypothesis, ia_response, evidence_for, evidence_against, consensus_score)
- `EvidenceBundle` (cache_hit, existing_mappings, conflict_mappings, source_context)
- `MemoryApprovalRequest` (3 campos obligatorios: admin_evidence_review bool, admin_justification String≥50, risk_acknowledgment bool+admin_session_id)
- `LearningPhase` (15 variantes del lifecycle)
- `MemoryQuery`, `MemoryLookupResult`
- `Hypothesis` (question, origin, proposed_destination, relation, source, priority)

**Contenido errors.rs**:
- `MemoryError` enum
- `HITLError` enum (EvidenceReviewRequired, JustificationTooShort{provided,required}, RiskAcknowledgmentRequired, SessionIdRequired)
- `DagAdapterError` enum

**Criterio**: Todos los tipos derivan Serialize, Deserialize, Archive, Clone, Debug

---

#### TAREA 1-f: graph.rs + SQLite Schema
**Tipo**: Rust nuevo
**Depende de**: 1-a, 1-e
**Archivos nuevos**:
- `zenic-v2/zenic-memory/src/graph.rs`

**Contenido**:
- `struct SemanticGraph` — SQLite-backed storage
- `fn init_schema()` — Crear tablas (semantic_mappings, ontology_base, learning_audit) con índices
- `fn store()` — Insertar nuevo mapeo
- `fn lookup()` — Buscar mapeo por origin + tenant_id
- `fn lookup_by_relation()` — Buscar por tipo de relación
- `fn approve()` — Marcar mapeo como aprobado
- `fn revoke()` — Revocar mapeo
- `fn increment_hit()` — Incrementar hit_count
- `fn list_by_tenant()` — Listar mapeos del tenant
- `fn store_audit()` — Registrar evento en learning_audit

**SQLite Schema** (del plan v3):
```sql
CREATE TABLE semantic_mappings (
    id TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    relation TEXT NOT NULL,
    destination TEXT NOT NULL,
    source TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    hit_count INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT,
    admin_justification TEXT,
    approved_at TEXT,
    merkle_hash TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(origin, relation, tenant_id)
);
CREATE TABLE ontology_base (...);
CREATE TABLE learning_audit (...);
+ 5 indexes
```

**Criterio**: Store/lookup/approve funcionan con SQLite. Hit_count se incrementa.

---

#### TAREA 1-g: cache.rs LRU rkyv
**Tipo**: Rust nuevo
**Depende de**: 1-a, 1-c, 1-e
**Archivos nuevos**:
- `zenic-v2/zenic-memory/src/cache.rs`

**Contenido**:
- `struct MemoryCache` — LRU cache con rkyv zero-copy
- Max 1000 entries por defecto
- Protegidos si hit_count > 20 (no se evict)
- `fn insert()` — Agregar mapeo al caché
- `fn lookup()` — Lookup en <1μs (rkyv archived access)
- `fn invalidate()` — Invalidar entrada
- `fn clear()` — Limpiar caché
- Serialización con bincode para persistencia rápida (opcional)

**Criterio**: Lookup <1ms medido. Eviction respeta hit_count > 20.

---

#### TAREA 1-h: dag_adapter.rs — Middleware Intercepción DAG
**Tipo**: Rust nuevo [GRIETA 1]
**Depende de**: 1-e, 1-f
**Archivos nuevos**:
- `zenic-v2/zenic-memory/src/dag_adapter.rs`

**Contenido** (especificación exacta del usuario):
- `struct DagAdapter { memory: Arc<SemanticGraph>, cache: Arc<MemoryCache> }`
- `fn try_adapt()`:
  1. Recibe nodo fallido + NodeOutput
  2. Extrae campo que causó el fallo del error_message
  3. Busca en caché LRU (<1μs)
  4. Si encontrado → inyecta parámetro corregido → retorna NodeOutput success
  5. Si no → busca en SQLite (<2ms)
  6. Si encontrado → caché + inyectar + success
  7. Si no → retorna None (dispara flujo de aprendizaje)
- `fn inject_mapping()` — Reemplazar clave origin por destination en payload
- `fn extract_failed_field()` — Parsear error_message para extraer campo fallido

**Modificación en context.rs**:
- `ExecutionContext` gana `dag_adapter: Option<Arc<DagAdapter>>`

**Criterio**: try_adapt resuelve "cobro → factura" en <2ms. None dispara aprendizaje.

---

#### TAREA 1-i: ontology.rs
**Tipo**: Rust nuevo
**Depende de**: 1-b, 1-f
**Archivos nuevos**:
- `zenic-v2/zenic-memory/src/ontology.rs`

**Contenido**:
- `struct OntologyManager`
- `fn load_base()` — Cargar base-es.yaml con include_str!()
- `fn get_opt_in_mappings()` — Obtener mapeos base para un tenant
- `fn check_override()` — Verificar si tenant tiene override local
- `fn set_opt_in()` — Activar/desactivar ontología para un tenant

**Criterio**: Ontología carga al inicio. Opt-in por tenant funciona.

---

#### TAREA 1-j: encode_rkyv en zenic-proto
**Tipo**: Rust modificación
**Depende de**: 1-c
**Archivos modificados**:
- `zenic-v2/zenic-proto/src/serde_.rs` — Agregar `encode_rkyv<T: Archive + Serialize>(val: &T) -> Vec<u8>` y `decode_rkyv<T>(bytes: &[u8]) -> Result<T::Archived>`

**Criterio**: encode_rkyv + decode_rkyv compilan y roundtrip correctamente.

---

### ═══════════════════════════════════════════
### FASE 2: Mecanismos + rkyv Hot Path
### ═══════════════════════════════════════════

---

#### TAREA 2-a: hypothesis.rs — Generador de Hipótesis
**Tipo**: Rust nuevo
**Depende de**: F1 completa
**Archivos nuevos**: `zenic-v2/zenic-memory/src/hypothesis.rs`

**Contenido**:
- `fn generate_schema_drift_hypotheses(lost_field, existing_fields, context) -> Vec<Hypothesis>`
  - Ejemplo: lost="estatus_cliente", existing=["id_usuario","estado_id",...] →
    - H1: "¿Es 'id_usuario' sinónimo de 'estatus_cliente'?" (priority: 3)
    - H2: "¿Es 'estado_id' sinónimo de 'estatus_cliente'?" (priority: 1, más probable)
- `fn generate_intent_hypotheses(user_intent, registered_tools, context) -> Vec<Hypothesis>`
  - Ejemplo: intent="tumba la cuenta", tools=["listar_usuarios","cancelar_suscripcion",...] →
    - H1: "¿'tumba la cuenta' equivale a 'listar_usuarios'?" (priority: 3)
    - H2: "¿'tumba la cuenta' equivale a 'cancelar_suscripcion'?" (priority: 1)
- `fn generate_policy_hypotheses(action_desc, policy_categories, context) -> Vec<Hypothesis>`
  - Ejemplo: desc="reparación urgente $500", categories=["gasto_crítico","gasto_menor",...] →
    - H1: "¿'reparación urgente por $500' se clasifica como 'gasto_crítico'?" (priority: 1)

**Criterio**: 3 funciones generan hipótesis correctas con priorización inteligente.

---

#### TAREA 2-b: schema_drift.rs — Mecanismo 1
**Tipo**: Rust nuevo
**Depende de**: 2-a
**Archivos nuevos**: `zenic-v2/zenic-memory/src/schema_drift.rs`

**Contenido**:
- `struct SchemaDriftDetector { graph, cache }`
- `fn detect(field_name, table_schema, tenant_id) -> Vec<Hypothesis>`
- `fn apply_mapping(mapping) -> Result<()>`

**Criterio**: Detecta "estatus_cliente" → genera hipótesis contra campos existentes.

---

#### TAREA 2-c: intent_routing.rs — Mecanismo 2
**Tipo**: Rust nuevo
**Depende de**: 2-a
**Archivos nuevos**: `zenic-v2/zenic-memory/src/intent_routing.rs`

**Contenido**:
- `struct IntentRoutingResolver { graph, cache }`
- `fn resolve(user_intent, mcp_tools, tenant_id) -> Vec<Hypothesis>`
- `fn register_synonym(synonym, tool_name) -> Result<()>`

**Criterio**: "tumba la cuenta" → hipótesis contra herramientas MCP.

---

#### TAREA 2-d: policy_refinement.rs — Mecanismo 3
**Tipo**: Rust nuevo
**Depende de**: 2-a
**Archivos nuevos**: `zenic-v2/zenic-memory/src/policy_refinement.rs`

**Contenido**:
- `struct PolicyRefinementEngine { graph, cache }`
- `fn classify(action_desc, policy_categories, tenant_id) -> Vec<Hypothesis>`

**Criterio**: "reparación urgente $500" → clasifica contra categorías de política.

---

#### TAREA 2-e: Policy Engine rkyv Hot Path
**Tipo**: Rust modificación
**Depende de**: 1-c
**Archivos modificados**:
- `zenic-v2/zenic-policy/Cargo.toml` — Agregar `rkyv = { workspace = true }`
- `zenic-v2/zenic-policy/src/engine.rs` — `evaluate_rkyv()` + derives
- `zenic-v2/zenic-policy/src/rule.rs` — rkyv derives
- `zenic-v2/zenic-policy/src/role.rs` — rkyv derives

**Criterio**: evaluate_rkyv() evalúa en <100μs sin deserialización completa.

---

#### TAREA 2-f: Safety Engine rkyv
**Tipo**: Rust modificación
**Depende de**: 1-d
**Archivos modificados**:
- `zenic-v2/zenic-safety/Cargo.toml` — Agregar `rkyv`
- `zenic-v2/zenic-safety/src/engine.rs` — Reemplazar `serde_json::Value` con `NodeValue`

**Criterio**: DomainSafetyGate usa NodeValue. validate_rkyv() funciona.

---

#### TAREA 2-g: Eliminar JSON.stringify en Evaluator
**Tipo**: TypeScript modificación
**Archivos modificados**:
- `gateway/policy-engine/evaluator.ts` — Reemplazar `JSON.stringify(request.context)` con BLAKE3 hash

**Criterio**: Cache key computation <5μs.

---

### ═══════════════════════════════════════════
### FASE 3: Verdict Pipeline Integration + PyO3 Bridge
### ═══════════════════════════════════════════

---

#### TAREA 3-a: verdict_adapter.rs
**Tipo**: Rust nuevo
**Depende de**: F1+F2
**Archivos nuevos**: `zenic-v2/zenic-memory/src/verdict_adapter.rs`

**Contenido**:
- `fn format_binary_question(hypothesis) -> String` — Formatea pregunta estricta SÍ/NO
- `fn process_ia_response(hypothesis, ia_response, evidence) -> LearningVerdict`

**Criterio**: Preguntas son binarias estrictas. Respuestas se convierten a LearningVerdict.

---

#### TAREA 3-b: PyO3 Bridge memory_chip.rs
**Tipo**: Rust nuevo
**Depende de**: F1+F2
**Archivos nuevos**: `zenic-v2/zenic-pybridge/src/memory_chip.rs`
**Archivos modificados**: `zenic-v2/zenic-pybridge/src/lib.rs` — Agregar módulo

**Contenido**:
- `#[pyclass] struct MemoryChip` — Wrapper PyO3
- `#[pymethods]` — lookup, store, approve, get_hypotheses, try_adapt, seal_learning

**Criterio**: Python puede llamar `_zenic_native.memory_chip_lookup()`. Sin JSON intermediario.

---

#### TAREA 3-c: _core.py Expandido — 9 Pasos [GRIETA 2]
**Tipo**: Python modificación
**Depende de**: 3-b (PyO3 bridge)
**Archivos modificados**: `src/core/verdict_parts/deterministic_pipeline/_core.py`

**Contenido** (especificación exacta del usuario):
- Agregar `memory_lookup()` — Paso 1 nuevo
- Agregar `dag_node_adapt()` — Paso 5 nuevo
- Agregar `set_memory_chip()` — Inyección PyO3
- Modificar `execute_all()` → `execute_all_expanded()` con 9 pasos estrictos
- Orden: memory_lookup → classify → extract → validate_schema → dag_node_adapt → check_rbac → gather_context → route_mcp → dry_run

**Criterio**: 9 pasos ejecutan en secuencia. memory_lookup cache hit bypasses IA.

---

#### TAREA 3-d: evidence_collector.py
**Tipo**: Python modificación
**Depende de**: 3-a
**Archivos modificados**: `src/core/verdict_parts/evidence_collector.py`

**Contenido**: Nuevo método `collect_memory_chip_evidence(query) -> Evidence` con tipo `CACHE_HIT`

**Criterio**: CACHE_HIT evidence inyectable con peso 1.3x.

---

#### TAREA 3-e: verdict_engine Pre-check
**Tipo**: Python modificación
**Depende de**: 3-a
**Archivos modificados**: `src/core/verdict_parts/verdict_engine/__init__.py`

**Contenido**:
- Antes del pipeline: consultar Memory Chip
- Si CACHE_HIT con confidence > 0.8 → retornar directamente (<5ms)
- Si no → flujo normal

**Criterio**: CACHE_HIT bypass funciona. Latencia <5ms medido.

---

#### TAREA 3-f: consensus_resolver.py
**Tipo**: Python modificación
**Depende de**: 3-a
**Archivos modificados**: `src/core/verdict_parts/consensus_resolver.py`

**Contenido**:
- Pesos dinámicos: hit_count > 20 → 1.5x, hit_count > 50 → 1.8x
- Si CACHE_HIT + confidence > 0.8 → resolver directo sin IA

**Criterio**: ConsensusResolver resuelve sin IA cuando hay CACHE_HIT fuerte.

---

#### TAREA 3-g: SharedMemoryBus rkyv Support
**Tipo**: Rust modificación
**Depende de**: 1-c
**Archivos modificados**: `zenic-v2/zenic-pybridge/src/bus.rs`

**Contenido**: Nuevo método `publish_rkyv<T: Archive>(&self, topic, data)`

**Criterio**: Bus soporta rkyv payloads manteniendo compatibilidad PyObject.

---

### ═══════════════════════════════════════════
### FASE 4: Cierre de Circuito — HITL + Merkle + YAML
### ═══════════════════════════════════════════

---

#### TAREA 4-a: hitl_bridge.rs — 3 Campos Obligatorios [GRIETA 3]
**Tipo**: Rust nuevo
**Archivos nuevos**: `zenic-v2/zenic-memory/src/hitl_bridge.rs`

**Contenido** (especificación exacta del usuario):
- `MemoryApprovalRequest` con validación estricta:
  - `admin_evidence_review: bool` — DEBE ser True
  - `admin_justification: String` — MÍNIMO 50 caracteres
  - `risk_acknowledgment: bool` — DEBE ser True
  - `admin_session_id: String` — ID criptográfico de sesión
- `fn validate()` → `Result<(), HITLError>` — Falla sin los 3 campos
- `fn create_approval_request()` — Crear request para HITL
- Excepción AUTO_APPROVE: solo SYNONYM_OF + confidence > 0.9 + hit_count > 10

**Criterio**: Justificación <50 chars → HITLError::JustificationTooShort. Risk sin session_id → rechazado.

---

#### TAREA 4-b: merkle_seal.rs
**Tipo**: Rust nuevo
**Archivos nuevos**: `zenic-v2/zenic-memory/src/merkle_seal.rs`

**Contenido**:
- `fn seal_mapping(mapping) -> Result<String>` — bincode serialize → BLAKE3 hash → return hash
- `fn verify_seal(mapping, expected_hash) -> bool` — Verificar integridad
- Anti-tampering: modificación invalida hash

**Criterio**: Seal con BLAKE3(bincode bytes). Verify detecta alteraciones.

---

#### TAREA 4-c: yaml_renderer.rs
**Tipo**: Rust nuevo
**Archivos nuevos**: `zenic-v2/zenic-memory/src/yaml_renderer.rs`

**Contenido**:
- `fn render_mapping(mapping, approval) -> String` — Genera YAML declarativo
- `fn validate_before_render(approval) -> Result<()>` — Verificar HITL válido
- Formato compatible con PolicyHotReloader existente
- Si MemoryApprovalRequest no valida → YAML no se genera

**Criterio**: YAML se renderiza solo si HITL valida. PolicyHotReloader lo detecta (30s).

---

#### TAREA 4-d: lifecycle.rs — Saga Workflow
**Tipo**: Rust nuevo
**Depende de**: 4-a, 4-b, 4-c
**Archivos nuevos**: `zenic-v2/zenic-memory/src/lifecycle.rs`

**Contenido**:
- `LearningWorkflow` — Ciclo completo como WorkflowDefinition
- Steps: Detect → MemoryLookup → DagAdapt → Hypothesize → Evidence → Consensus → Verdict → HITL → RenderYAML → SealMerkle → CacheResult → Complete
- Compensation: HITL rechaza → eliminar mapeo + rollback YAML
- Compensation: MerkleLedger falla → rollback YAML

**Criterio**: Workflow completa ciclo. Compensation funciona en rechazo.

---

#### TAREA 4-e: chain.py Integración
**Tipo**: Python modificación
**Depende de**: 4-a
**Archivos modificados**: `src/core/approval/chain.py`

**Contenido**:
- Nuevo `MemoryApprovalPayload` dataclass con 3 campos obligatorios
- Integrar con ApprovalChain.create_request() usando metadata
- Validar payload antes de aprobar

**Criterio**: chain.py rechaza aprobaciones sin justificación ≥50 chars.

---

#### TAREA 4-f: TheoremCache bincode
**Tipo**: Python/Rust modificación
**Archivos modificados**:
- `src/core/level8_theorem_cache/cache.py` — Usar bincode via _zenic_native
- `native/src/lib.rs` — Agregar theorem_cache_serialize/deserialize

**Criterio**: TheoremCache usa bincode. ~60% menos tamaño, ~3x más rápido.

---

### ═══════════════════════════════════════════
### FASE 5: Subscription + API + Bridge
### ═══════════════════════════════════════════

---

#### TAREA 5-a: subscription_gate.rs
**Tipo**: Rust nuevo
**Archivos nuevos**: `zenic-v2/zenic-memory/src/subscription_gate.rs`

**Contenido**:
- Feature gates por tier:
  - Starter: SchemaDrift (10/mes, LRU 100)
  - Business: +IntentRouting (50/mes, LRU 500)
  - Enterprise: +PolicyRefinement +Ontología (ilimitado, LRU 2000)
  - On-Premise: +Export/Import +Custom (ilimitado)
- `fn check_access(tier, mechanism) -> Result<(), SubscriptionError>`
- `fn check_usage_limit(tier, usage_count) -> bool`

**Criterio**: Starter bloqueado para Intent Routing. Enterprise accede a todo.

---

#### TAREA 5-b: 9 API Routes
**Tipo**: TypeScript nuevo
**Archivos nuevos** (9):
- `gateway/src/app/api/v1/memory/lookup/route.ts`
- `gateway/src/app/api/v1/memory/hypothesize/route.ts`
- `gateway/src/app/api/v1/memory/mappings/route.ts`
- `gateway/src/app/api/v1/memory/approve/[id]/route.ts`
- `gateway/src/app/api/v1/memory/reject/[id]/route.ts`
- `gateway/src/app/api/v1/memory/ontology/route.ts`
- `gateway/src/app/api/v1/memory/stats/route.ts`
- `gateway/src/app/api/v1/memory/audit/[id]/route.ts`
- `gateway/src/app/api/v1/memory/opt-in/route.ts`

**Criterio**: 9 endpoints responden. Subscription gates verificados.

---

#### TAREA 5-c: TS↔Rust Policy Bridge
**Tipo**: TypeScript + Rust
**Archivos modificados**:
- `gateway/policy-engine/evaluator.ts` — YAML → bincode → Rust bridge
- Eliminar 4x JSON.parse() en policy load

**Criterio**: Policies cargadas vía bincode desde Rust. JSON.parse eliminado.

---

#### TAREA 5-d: Actualizar zenic-subscription
**Tipo**: Rust modificación
**Depende de**: 5-a
**Archivos modificados**:
- `zenic-v2/zenic-subscription/src/feature_gates.rs` — Nuevos gates
- `zenic-v2/zenic-subscription/src/usage.rs` — Nuevos types

**Criterio**: memory_chip_basic, memory_chip_advanced, memory_chip_ontology, memory_chip_export disponibles.

---

## ═══════════════════════════════════════════
## CRONOGRAMA ESTIMADO
## ═══════════════════════════════════════════

| Fase | Tareas | Paralelismo | Estimación |
|------|--------|-------------|-----------|
| F1 | 10 tareas (1-a..1-j) | 4 paralelas máximo | ~1,800 LOC Rust + 50 YAML |
| F2 | 7 tareas (2-a..2-g) | 3 paralelas máximo | ~1,200 LOC Rust + 50 TS |
| F3 | 7 tareas (3-a..3-g) | 3 paralelas máximo | ~500 LOC Rust + 200 Python |
| F4 | 6 tareas (4-a..4-f) | 3 paralelas máximo | ~700 LOC Rust + 100 Python |
| F5 | 4 tareas (5-a..5-d) | 3 paralelas máximo | ~250 LOC Rust + 450 TS |
| **Total** | **34 tareas** | | **~5,500 LOC** |

---

## ═══════════════════════════════════════════
## CHECKPOINTS DE VERIFICACIÓN
## ═══════════════════════════════════════════

### CP1: Fin Fase 1
- [ ] `cargo build -p zenic-memory` ✅
- [ ] `cargo build -p zenic-proto` con rkyv ✅
- [ ] `cargo build -p zenic-runtime` con NodeValue ✅
- [ ] LRU cache lookup <1ms ✅
- [ ] Ontología base carga ✅
- [ ] DagAdapter.try_adapt() funciona ✅

### CP2: Fin Fase 2
- [ ] 3 mecanismos generan hipótesis ✅
- [ ] Policy eval <100μs ✅
- [ ] Cache key <5μs ✅

### CP3: Fin Fase 3
- [ ] Flujo end-to-end: error → hipótesis → veredicto IA → HITL ✅
- [ ] CACHE_HIT bypass <5ms ✅
- [ ] 9 pasos pipeline ejecutan ✅
- [ ] PyO3 bridge funciona ✅

### CP4: Fin Fase 4
- [ ] HITL rechaza justificación <50 chars ✅
- [ ] MerkleLedger sella con BLAKE3 ✅
- [ ] YAML se renderiza + hot-reload ✅
- [ ] Lifecycle completa con compensation ✅

### CP5: Fin Fase 5
- [ ] Feature gates por tier ✅
- [ ] 9 API routes responden ✅
- [ ] TS↔Rust bridge funciona ✅
- [ ] `git push origin main` ✅
- [ ] Tag `v3.1.0` ✅

---

*Plan de Ejecución — Zenic-Agents v3.0.0 — 34 Tareas, 5 Fases, 5 Checkpoints*
