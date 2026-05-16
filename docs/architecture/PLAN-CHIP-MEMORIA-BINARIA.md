# PLAN DE IMPLEMENTACIÓN — Chip de Memoria Adaptativa Binaria + Flujo de 4 Capas
## Zenic-Agents v3.0.0

---

## Resumen Ejecutivo

Implementar el **Chip de Memoria Adaptativa Binaria** como un nuevo crate Rust (`zenic-memory`) con 3 mecanismos de aprendizaje (Schema Drift, Intent Routing, Policy Refinement), integrado en las 4 capas del Verdict Pipeline existente, con persistencia SQLite local, YAML hot-reload, validación HITL obligatoria y sellado MerkleLedger.

**Restricciones**: Offline, CPU-only, ARM64, 500MB RAM, Qwen3-0.6B, IA solo responde SÍ/NO.

---

## Hallazgos Clave del Análisis del Código Existente

### Puntos de Integración ya Existentes (¡No hay que crearlos desde cero!)

| # | Componente | Archivo | Lo que YA existe | Cómo se conecta el Chip |
|---|-----------|---------|------------------|------------------------|
| 1 | **EvidenceCollector** | `src/core/verdict_parts/evidence_collector.py` | `EvidenceType.CACHE_HIT` enum (peso 1.3x) | El Chip inyecta evidencia `CACHE_HIT` cuando encuentra mapeo aprendido |
| 2 | **ConsensusResolver** | `src/core/verdict_parts/consensus_resolver.py` | Scoring ponderado con thresholds (0.3/0.6/0.85) | El Chip ajusta pesos basado en frecuencia de acierto del mapeo |
| 3 | **VerdictEngine** | `src/core/verdict_parts/verdict_engine/__init__.py` | `ask_yes_no()` — ya emite veredicto binario | El Chip genera las hipótesis que alimentan `ask_yes_no()` |
| 4 | **TheoremCache** | `src/core/level8_theorem_cache/cache.py` | Skeleton hash + LRU (500 entries, hit>50 protegidas) | El Chip alimenta TheoremCache con veredictos aprendidos |
| 5 | **MerkleLedger** | `src/core/level7_merkle_ledger/ledger/_core.py` | BLAKE3 hashing, tenant_id, tabla `ledger` | Cada aprendizaje HITL-aprobado se sella con `commit()` |
| 6 | **Policy Hot-Reload** | `gateway/policy-engine/hot-reload.ts` | `PolicyHotReloader` (30s polling, hash change detection) | Reglas aprendidas se inyectan vía YAML + hot-reload |
| 7 | **HITL AUTO_APPROVE** | `gateway/hitl/approval-engine.ts` | 5 modos incluyendo `AUTO_APPROVE` con reglas | Mapeos de bajo riesgo pueden auto-aprobarse con evidencia |
| 8 | **Safety Gate** | `zenic-v2/zenic-safety/src/engine.rs` | 4-layer pipeline, 35 domain rules | Reglas aprendidas de seguridad se inyectan como `DomainRuleSet` |
| 9 | **WorkflowEngine** | `zenic-v2/zenic-flow/src/engine.rs` | Saga + checkpoint + compensation | Flujo de aprendizaje como `WorkflowDefinition` con compensación |
| 10 | **Subscription Feature Gates** | `zenic-v2/zenic-subscription/src/feature_gates.rs` | `check_feature()` por tier | Feature gate para mecanismos avanzados del Chip |

### Lo que YA existe pero necesita REFACTORIZARSE

| Componente | Problema | Solución |
|-----------|----------|----------|
| `src/core/learning/learning_engine.py` | LearningEngine genérico, no integrado con el Verdict Pipeline | Conectar como consumidor del Chip |
| `src/core/smart_memory.py` | Memoria conversacional, no determinista/binary | Mantener separado (memoria conversacional ≠ memoria de aprendizaje binario) |
| `src/core/conversational/routing/intent_engine.py` | Enrutamiento de intenciones sin aprendizaje | Conectar con Mecanismo 2 del Chip |

---

## Arquitectura del Nuevo Crate: `zenic-memory`

```
zenic-v2/zenic-memory/
├── Cargo.toml
└── src/
    ├── lib.rs                    # Public API del crate
    ├── types.rs                  # Core types: SemanticMapping, LearningVerdict, MemoryEntry
    ├── errors.rs                 # Error types
    ├── graph.rs                  # Semantic Graph Engine (SQLite-backed)
    ├── ontology.rs               # Shared Ontology Layer (base mappings, opt-in)
    ├── cache.rs                  # Hot-path LRU cache (<5ms lookup)
    ├── hypothesis.rs             # Hypothesis Generator (structured proposals for IA)
    ├── schema_drift.rs           # Mecanismo 1: Schema Drift Detection
    ├── intent_routing.rs         # Mecanismo 2: Intent Synonym Resolution
    ├── policy_refinement.rs      # Mecanismo 3: Policy Gray-Area Classification
    ├── verdict_adapter.rs        # Bridge to VerdictEngine.ask_yes_no()
    ├── hitl_bridge.rs            # Bridge to HITL approval flow
    ├── merkle_seal.rs            # MerkleLedger integration for learning audit
    ├── yaml_renderer.rs          # Render learned rules to YAML for hot-reload
    ├── subscription_gate.rs      # Feature gating by subscription tier
    └── lifecycle.rs              # Full learning lifecycle: detect → hypothesize → verdict → HITL → seal → cache
```

---

## FASES DE IMPLEMENTACIÓN

### FASE 1: Fundación — Core Types + Semantic Graph (Rust)
**Duración estimada**: Paso más largo — es la base de todo

**Entregables**:
1. **Nuevo crate `zenic-memory`** en el workspace `zenic-v2/`
2. **`types.rs`** — Tipos core:
   ```rust
   struct SemanticMapping {
       id: Uuid,
       origin: String,           // ej: "estatus_cliente"
       relation: MappingRelation, // ej: SYNONYM_OF, EQUIVALENT_TO, ROUTES_TO
       destination: String,      // ej: "estado_id"
       source: MappingSource,    // SCHEMA_DRIFT, INTENT_ROUTING, POLICY_REFINEMENT
       tenant_id: TenantId,
       confidence: f64,          // 0.0-1.0, sube con cada validación
       hit_count: u32,           // veces que se ha usado exitosamente
       approved_by: Option<String>, // HITL approver
       approved_at: Option<chrono::DateTime<Utc>>,
       merkle_hash: Option<String>, // BLAKE3 seal
       created_at: chrono::DateTime<Utc>,
   }

   enum MappingRelation {
       SynonymOf,        // "tumba" ↔ "cancelar"
       EquivalentTo,     // "estatus_cliente" ↔ "estado_id"
       RoutesTo,         // intención → herramienta MCP
       ClassifiesAs,     // "reparación urgente" → "gasto crítico"
       Overrides,        // tenant override de ontología base
   }

   enum MappingSource {
       SchemaDrift,      // Mecanismo 1
       IntentRouting,    // Mecanismo 2
       PolicyRefinement, // Mecanismo 3
       OntologyBase,     // Ontología compartida
       ManualEntry,      // Admin manual
   }

   struct LearningVerdict {
       mapping: SemanticMapping,
       hypothesis: String,       // La pregunta que se le hizo a la IA
       ia_response: bool,        // SÍ/NO de Qwen3-0.6B
       evidence_for: Vec<String>,
       evidence_against: Vec<String>,
       consensus_score: f64,     // Score del ConsensusResolver
   }

   struct MemoryQuery {
       origin: String,
       relation: Option<MappingRelation>,
       tenant_id: TenantId,
       source: Option<MappingSource>,
   }

   struct MemoryLookupResult {
       mapping: SemanticMapping,
       cache_hit: bool,          // true = resuelto sin IA
       lookup_time_us: u64,      // microsegundos
   }
   ```

3. **`graph.rs`** — Semantic Graph Engine:
   - SQLite-backed storage (misma DB que policy_code, tabla nueva)
   - Schema SQL:
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
         approved_at TEXT,
         merkle_hash TEXT,
         created_at TEXT NOT NULL,
         UNIQUE(origin, relation, tenant_id)
     );
     CREATE INDEX idx_sm_origin ON semantic_mappings(origin, tenant_id);
     CREATE INDEX idx_sm_destination ON semantic_mappings(destination, tenant_id);
     CREATE INDEX idx_sm_source ON semantic_mappings(source, tenant_id);

     CREATE TABLE ontology_base (
         id TEXT PRIMARY KEY,
         origin TEXT NOT NULL,
         relation TEXT NOT NULL,
         destination TEXT NOT NULL,
         domain TEXT NOT NULL,
         language TEXT NOT NULL DEFAULT 'es',
         created_at TEXT NOT NULL,
         UNIQUE(origin, relation, domain)
     );

     CREATE TABLE learning_audit (
         id TEXT PRIMARY KEY,
         mapping_id TEXT NOT NULL,
         action TEXT NOT NULL,        -- PROPOSED, IA_APPROVED, HITL_APPROVED, HITL_REJECTED, SEALED, REVOKED
         actor TEXT NOT NULL,          -- system, ia, admin_email
         evidence_json TEXT NOT NULL,
         timestamp TEXT NOT NULL,
         FOREIGN KEY (mapping_id) REFERENCES semantic_mappings(id)
     );
     ```
   - Operaciones: `store()`, `lookup()`, `lookup_by_relation()`, `approve()`, `revoke()`, `increment_hit()`, `list_by_tenant()`

4. **`cache.rs`** — Hot-path LRU cache:
   - En-memory LRU (max 1000 mappings, protegidos si hit_count > 20)
   - Lookup en <1ms (antes de tocar SQLite)
   - Invalidación automática cuando se aprueba/revoca un mapeo
   - Serialización con bincode para persistencia rápida

5. **`errors.rs`** — Error types

6. **`ontology.rs`** — Shared Ontology Layer:
   - ~50 mapeos base universales en español (sinónimos comunes, abreviaturas)
   - Cargo como YAML embebido en el binario (include_str!)
   - Un tenant puede override local de cualquier mapeo base
   - Opt-in: el tenant elige si hereda la ontología base

**Criterio de Aceptación**:
- `cargo build -p zenic-memory` compila sin errores
- Tests unitarios de store/lookup/approve en SQLite
- LRU cache lookup <1ms medido
- Ontología base carga desde YAML embebido

---

### FASE 2: Los 3 Mecanismos de Aprendizaje (Rust)
**Depende de**: FASE 1

**Entregables**:

1. **`schema_drift.rs`** — Mecanismo 1: Schema Drift Detection:
   ```rust
   struct SchemaDriftDetector {
       graph: SemanticGraph,
       cache: MemoryCache,
   }
   // Flujo:
   // 1. Recibe error de ejecución (columna/tabla no encontrada)
   // 2. Extrae nombres existentes del schema actual (Python pasa esta info)
   // 3. Genera hipótesis: "¿Es X sinónimo de Y?" para cada candidato
   // 4. Devuelve Vec<Hypothesis> para alimentar al VerdictEngine
   ```

2. **`intent_routing.rs`** — Mecanismo 2: Intent Synonym Resolution:
   ```rust
   struct IntentRoutingResolver {
       graph: SemanticGraph,
       cache: MemoryCache,
       tool_registry: Vec<ToolDescriptor>,  // herramientas MCP registradas
   }
   // Flujo:
   // 1. Recibe intent del usuario que no matchea herramienta directa
   // 2. Busca en caché/grafo si ya existe sinónimo aprendido
   // 3. Si no existe, genera hipótesis contra cada herramienta registrada
   // 4. Devuelve Vec<Hypothesis> para alimentar al VerdictEngine
   ```

3. **`policy_refinement.rs`** — Mecanismo 3: Policy Gray-Area Classification:
   ```rust
   struct PolicyRefinementEngine {
       graph: SemanticGraph,
       cache: MemoryCache,
   }
   // Flujo:
   // 1. Recibe acción que el PolicyEngine no puede clasificar determinísticamente
   // 2. Genera hipótesis contra las categorías de políticas existentes
   // 3. Devuelve Vec<Hypothesis> para alimentar al VerdictEngine
   ```

4. **`hypothesis.rs`** — Hypothesis Generator (compartido por los 3 mecanismos):
   ```rust
   struct Hypothesis {
       question: String,          // La pregunta binaria exacta para el LLM
       origin: String,            // Lo que se busca
       proposed_destination: String, // Lo que se propone como equivalente
       relation: MappingRelation,
       source: MappingSource,
       priority: u32,             // Orden de evaluación
   }

   struct HypothesisGenerator;

   impl HypothesisGenerator {
       fn generate_schema_drift_hypotheses(
           lost_field: &str,
           existing_fields: &[String],
           context: &SchemaContext,
       ) -> Vec<Hypothesis>;

       fn generate_intent_hypotheses(
           user_intent: &str,
           registered_tools: &[ToolDescriptor],
           context: &IntentContext,
       ) -> Vec<Hypothesis>;

       fn generate_policy_hypotheses(
           action_description: &str,
           policy_categories: &[PolicyCategory],
           context: &PolicyContext,
       ) -> Vec<Hypothesis>;
   }
   ```

**Criterio de Aceptación**:
- Los 3 mecanismos generan hipótesis correctas
- Priorización inteligente (los más probables primero)
- Si el caché tiene el mapeo, NO genera hipótesis (resuelve directo)
- Tests unitarios para cada mecanismo con datos de prueba

---

### FASE 3: Integración con Verdict Pipeline (Rust + Python)
**Depende de**: FASE 2

**Entregables**:

1. **`verdict_adapter.rs`** — Bridge al VerdictEngine:
   ```rust
   struct VerdictAdapter;

   impl VerdictAdapter {
       // Toma una hipótesis y la formatea como pregunta binaria
       fn format_binary_question(hypothesis: &Hypothesis) -> String;

       // Toma la respuesta SÍ/NO del LLM y la convierte en LearningVerdict
       fn process_ia_response(
           hypothesis: &Hypothesis,
           ia_response: bool,
           evidence: &EvidenceBundle,
       ) -> LearningVerdict;
   }
   ```

2. **Modificación en Python** — `src/core/verdict_parts/evidence_collector.py`:
   - Nuevo método `collect_memory_chip_evidence(query: MemoryQuery) -> Evidence`
   - Cuando el Memory Chip encuentra un mapeo, inyecta evidencia tipo `CACHE_HIT`
   - Esto permite que el ConsensusResolver resuelva sin invocar al LLM

3. **Modificación en Python** — `src/core/verdict_parts/verdict_engine/__init__.py`:
   - Antes de ejecutar el pipeline completo, consultar al Memory Chip
   - Si hay `CACHE_HIT` con confidence > 0.8, saltar LLM (resolución en <5ms)
   - Si no hay cache, alimentar hipótesis del Chip al flujo normal

4. **PyO3 Bridge** — Extender `zenic-pybridge`:
   - Nuevo módulo `memory_chip` en `zenic-v2/zenic-pybridge/src/memory_chip.rs`
   - Expone: `lookup()`, `store()`, `approve()`, `get_hypotheses()`, `seal_learning()`
   - Python llama a Rust para todas las operaciones del Chip

**Criterio de Aceptación**:
- Flujo end-to-end: error de schema → hipótesis → veredicto IA → HITL → sellado
- `CACHE_HIT` bypass del LLM funciona (latencia <5ms)
- PyO3 bridge compila y Python puede llamar a Rust
- Test de integración con el VerdictEngine existente

---

### FASE 4: HITL + MerkleLedger + YAML Hot-Reload (Rust + Python + TS)
**Depende de**: FASE 3

**Entregables**:

1. **`hitl_bridge.rs`** — Bridge al HITL:
   - Cuando la IA responde SÍ, se crea un `ApprovalRequest` con:
     - La hipótesis evaluada
     - La evidencia (pro + contra)
     - El veredicto de la IA
     - La propuesta de mapeo resultante
   - Modo de aprobación: `SINGLE` (1 clic del admin)
   - Para mapeos de baja criticidad con confidence > 0.9 y hit_count > 10: `AUTO_APPROVE`

2. **`merkle_seal.rs`** — Sellado MerkleLedger:
   - Después de HITL approval, se sella el mapeo:
     - Calcular BLAKE3 hash del mapeo (origin + relation + destination + tenant_id)
     - Commit al MerkleLedger existente
     - Actualizar `merkle_hash` en `semantic_mappings`
   - Anti-tampering: cualquier modificación no autorizada invalida el hash

3. **`yaml_renderer.rs`** — Renderizado a YAML:
   - Convierte un `SemanticMapping` aprobado a regla YAML declarativa
   - Formato compatible con el Policy Engine existente
   - Escribir al directorio de políticas para hot-reload automático
   ```yaml
   # Auto-generated by zenic-memory (Mecanismo: schema_drift)
   # Approved by: admin@empresa.com at 2025-01-15T10:30:00Z
   # Merkle seal: blake3:a4f2c8...
   ---
   apiVersion: zenic.agents/v1
   kind: SemanticMapping
   metadata:
     id: "uuid-here"
     source: schema_drift
     tenant: "empresa-a"
   spec:
     origin: "estatus_cliente"
     relation: "equivalent_to"
     destination: "estado_id"
     confidence: 0.95
   ```

4. **`lifecycle.rs`** — Ciclo de vida completo del aprendizaje:
   ```rust
   enum LearningPhase {
       Detecting,        // Capa 1: Deteco analítico
       GeneratingHypotheses,  // Hipótesis estructuradas
       CollectingEvidence,    // Capa 2: EvidenceCollector
       ResolvingConsensus,    // Capa 3: ConsensusResolver
       AwaitingVerdict,      // Capa 4: VerdictEngine (IA SÍ/NO)
       AwaitingHITL,         // HITL validación humana
       RenderingYAML,        // Compilación a YAML
       SealingMerkle,        // Sellado criptográfico
       CachingResult,        // Escritura en caché LRU
       Complete,             // Listo para <5ms la próxima vez
       Failed(LearningError),
       Compensating,         // Rollback si algo falla (Saga)
   }

   struct LearningWorkflow {
       phase: LearningPhase,
       mapping: Option<SemanticMapping>,
       verdict: Option<LearningVerdict>,
       hitl_request_id: Option<String>,
       merkle_hash: Option<String>,
       started_at: chrono::DateTime<Utc>,
   }
   ```

5. **Integración con `zenic-flow`** — El learning lifecycle como WorkflowDefinition:
   - Cada proceso de aprendizaje es un workflow con steps y compensations
   - Si HITL rechaza → compensation: eliminar mapeo propuesto
   - Si MerkleLedger falla → compensation: rollback del YAML

**Criterio de Aceptación**:
- HITL approval flow funciona (create → approve/reject)
- MerkleLedger sella cada aprendizaje aprobado
- YAML se renderiza y el PolicyHotReloader lo detecta
- LearningWorkflow completa ciclo completo: detect → seal → cache
- Compensation (rollback) funciona si HITL rechaza

---

### FASE 5: Subscription Feature Gates + API Routes (Rust + TS)
**Depende de**: FASE 4

**Entregables**:

1. **`subscription_gate.rs`** — Feature gates por tier:
   ```rust
   // Mapeo de mecanismos por tier
   Starter:     Schema Drift (básico, 10 mapeos/mes)
   Business:    Schema Drift + Intent Routing (50 mapeos/mes)
   Enterprise:  Los 3 mecanismos + Ontología compartida (ilimitado)
   On-Premise:  Los 3 mecanismos + Ontología + Export/Import + Custom rules
   ```

2. **API Routes** (TypeScript Gateway):
   - `POST /api/v1/memory/lookup` — Buscar mapeo semántico
   - `POST /api/v1/memory/hypothesize` — Generar hipótesis
   - `GET  /api/v1/memory/mappings` — Listar mapeos del tenant
   - `POST /api/v1/memory/approve/:id` — HITL approval
   - `POST /api/v1/memory/reject/:id` — HITL rejection
   - `DELETE /api/v1/memory/mappings/:id` — Revocar mapeo
   - `GET  /api/v1/memory/ontology` — Ver ontología base
   - `POST /api/v1/memory/ontology/opt-in` — Opt-in a ontología compartida
   - `GET  /api/v1/memory/stats` — Estadísticas de aprendizaje
   - `GET  /api/v1/memory/audit/:id` — Audit trail de un mapeo

3. **Modificación en `zenic-subscription`**:
   - Nuevos feature gates: `memory_chip_basic`, `memory_chip_advanced`, `memory_chip_ontology`, `memory_chip_export`
   - Nuevos usage types: `MEMORY_LOOKUPS`, `MEMORY_HYPOTHESES`, `MEMORY_MAPPINGS`

**Criterio de Aceptación**:
- Feature gates bloquean mecanismos según tier
- API routes responden correctamente
- Rate limiting por tier funciona
- Test end-to-end con diferentes tiers

---

## Diagrama de Dependencias entre Fases

```
FASE 1: Core Types + Semantic Graph + Cache + Ontology
   │
   ▼
FASE 2: 3 Mecanismos + Hypothesis Generator
   │
   ▼
FASE 3: Verdict Adapter + PyO3 Bridge + Evidence Injection
   │
   ▼
FASE 4: HITL Bridge + Merkle Seal + YAML Render + Lifecycle
   │
   ▼
FASE 5: Subscription Gates + API Routes
```

## Archivos Nuevos vs Modificados

### Archivos Nuevos (Rust crate zenic-memory)
```
zenic-v2/zenic-memory/Cargo.toml
zenic-v2/zenic-memory/src/lib.rs
zenic-v2/zenic-memory/src/types.rs
zenic-v2/zenic-memory/src/errors.rs
zenic-v2/zenic-memory/src/graph.rs
zenic-v2/zenic-memory/src/ontology.rs
zenic-v2/zenic-memory/src/cache.rs
zenic-v2/zenic-memory/src/hypothesis.rs
zenic-v2/zenic-memory/src/schema_drift.rs
zenic-v2/zenic-memory/src/intent_routing.rs
zenic-v2/zenic-memory/src/policy_refinement.rs
zenic-v2/zenic-memory/src/verdict_adapter.rs
zenic-v2/zenic-memory/src/hitl_bridge.rs
zenic-v2/zenic-memory/src/merkle_seal.rs
zenic-v2/zenic-memory/src/yaml_renderer.rs
zenic-v2/zenic-memory/src/subscription_gate.rs
zenic-v2/zenic-memory/src/lifecycle.rs
```

### Archivos Nuevos (PyO3 bridge)
```
zenic-v2/zenic-pybridge/src/memory_chip.rs
```

### Archivos Nueivos (Ontología base YAML)
```
zenic-v2/zenic-memory/ontology/base-es.yaml
```

### Archivos Nuevos (API Routes)
```
gateway/src/app/api/v1/memory/lookup/route.ts
gateway/src/app/api/v1/memory/hypothesize/route.ts
gateway/src/app/api/v1/memory/mappings/route.ts
gateway/src/app/api/v1/memory/approve/[id]/route.ts
gateway/src/app/api/v1/memory/reject/[id]/route.ts
gateway/src/app/api/v1/memory/ontology/route.ts
gateway/src/app/api/v1/memory/stats/route.ts
gateway/src/app/api/v1/memory/audit/[id]/route.ts
```

### Archivos Modificados (Integración)
```
zenic-v2/Cargo.toml                                    # Agregar zenic-memory al workspace
zenic-v2/zenic-pybridge/src/lib.rs                     # Agregar módulo memory_chip
zenic-v2/zenic-subscription/src/feature_gates.rs       # Nuevos feature gates
zenic-v2/zenic-subscription/src/usage.rs               # Nuevos usage types
src/core/verdict_parts/evidence_collector.py            # collect_memory_chip_evidence()
src/core/verdict_parts/verdict_engine/__init__.py       # Memory Chip lookup before pipeline
src/core/verdict_parts/consensus_resolver.py            # Dynamic weight adjustment
native/src/lib.rs                                       # Exponer zenic-memory via _zenic_native
```

---

## Restricciones Técnicas Respetadas

| Restricción | Cómo se respeta |
|-------------|----------------|
| Offline | Todo en SQLite local + YAML local. Sin cloud. |
| CPU-only | Sin GPU. LLM solo emite 1 token (SÍ/NO). |
| ARM64 / Android-Termux | Rust compila nativo para ARM64. SQLite embebido. |
| 500MB RAM | LRU cache con límite duro (1000 entries). SQLite WAL mode. |
| Qwen3-0.6B | Solo se invoca para empates. 1 token = mínima latencia. |
| IA solo SÍ/NO | VerdictAdapter.formula preguntas binarias estrictas. |
| <5ms gateway | Cache lookup <1ms + SQLite <2ms = bien dentro del budget. |
| MerkleLedger audit | Cada aprendizaje aprobado se sella con BLAKE3. |
| HITL obligatorio | Ningún mapeo se activa sin aprobación humana. |
| Hot-reload | YAML → PolicyHotReloader detecta cambios en 30s. |

---

## Estimación de Líneas de Código

| Fase | Rust | Python | TypeScript | Total |
|------|------|--------|------------|-------|
| Fase 1 | ~1,200 | 0 | 0 | ~1,200 |
| Fase 2 | ~800 | 0 | 0 | ~800 |
| Fase 3 | ~400 | ~200 | 0 | ~600 |
| Fase 4 | ~600 | ~100 | ~50 | ~750 |
| Fase 5 | ~200 | 0 | ~400 | ~600 |
| **Total** | **~3,200** | **~300** | **~450** | **~3,950** |

---

*Plan generado como parte de Zenic-Agents v3.0.0 — Implementation Blueprint*
