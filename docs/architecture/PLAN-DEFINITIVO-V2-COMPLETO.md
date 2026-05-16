# ═══════════════════════════════════════════════════════════════════
# PLAN DEFINITIVO — Chip Binario + 4 Capas Veredicto + rkyv/bincode
# Zenic-Agents v3.0.0 — Blueprint Unificado v2
# ═══════════════════════════════════════════════════════════════════
#
# TRAZABILIDAD EXPLICITA: Cada sección marca de qué texto viene [T1/T2/T3]
# T1 = Texto 1: Chip de Memoria Adaptativa Binaria
# T2 = Texto 2: Flujo de Aprendizaje bajo las 4 Capas del Veredicto
# T3 = Texto 3: Serialización rkyv + bincode
# ═══════════════════════════════════════════════════════════════════

---

## 0. PRINCIPIOS INVARIABLES [T1+T2]

> **La Capa Estructurada Propone, la IA Clasifica (Sí/No) y el Humano Valida.** [T1]

1. El LLM NUNCA genera contenido — solo emite veredicto booleano [T1+T2]
2. La memoria NO altera los pesos del LLM — modifica la config del DAG y Policy Engine [T2]
3. Sin cloud, sin APIs externas — Offline, CPU-only, ARM64, 500MB RAM, Qwen3-0.6B [T2]
4. Tecnología descartada: vectoriales cloud, Neo4j, almacenamiento agéntico comercial [T2]
5. rkyv para tránsito (zero-copy), bincode para persistencia (compacto), serde_json solo para APIs [T3]

---

## 1. ARQUITECTURA DEL CHIP BINARIO [T1]

### 1.1 Grafo de Mapeo Semántico [T1]

Registros de tipo `Origen → Relación → Destino` validados, almacenados en SQLite local.

```
Ejemplos:
  "estatus_cliente" → SYNONYM_OF → "estado_id"          [Mecanismo 1: Schema Drift]
  "tumba la cuenta" → ROUTES_TO   → "cancelar_suscripcion" [Mecanismo 2: Intent Routing]
  "reparación urgente" → CLASSIFIES_AS → "gasto_crítico"    [Mecanismo 3: Policy Refinement]
```

### 1.2 Modelo Híbrido de Grafo [T1]

- **Grafo por tenant (aislado)**: Cada DB de usuario tiene su propio grafo. El aprendizaje de un cliente NO contamina al de otro.
- **Capa de Ontología Compartida (opt-in)**: ~50 mapeos universales en español (sinónimos, abreviaturas). El tenant puede heredar y sobreescribir localmente.

### 1.3 Los 3 Mecanismos de Aprendizaje [T1]

**Mecanismo 1: Schema Drift** — El DAG Core busca un campo que ya no existe → código detecta error → extrae columnas actuales → IA evalúa cada una → HITL aprueba → se guarda el mapeo → la próxima vez se resuelve en microsegundos sin IA.

**Mecanismo 2: Intent Routing** — Usuario usa jerga ambigua → código no encuentra herramienta MCP directa → IA evalúa contra herramientas registradas → HITL aprueba sinónimo → la próxima vez se enruta directo.

**Mecanismo 3: Policy Refinement** — Escenario gris en Policy Engine → IA clasifica si la acción entra en una categoría de política → se aplica bloqueo (fail-safe) → HITL aprueba clasificación → la próxima vez se clasifica determinísticamente.

### 1.4 Flujo de Datos Completo [T1]

```
[Entrada de Datos/Error]
       │
       ▼
[Capa Determinista: Python] ──(Busca en caché de memoria local)──► [¿Existe relación?]
       │                                                           │
       │                                                    ┌──────┴──────┐
       │ NO                                                SÍ            NO
       ▼                                                    │             │
[Generador de Hipótesis Estructuradas]                [Ejecuta en     [Ejecuta Acción
       │                                               Rust a          con regla
       ▼                                              Wire-Speed]     existente]
[Filtro IA: Evaluación SÍ/NO]
       │
       ▼ SÍ
[Módulo HITL: Validación Humana de 1-Clic]
       │
       ▼
[Escritura en Grafo de Memoria (SQLite/Local)] ──► (El sistema ya aprendió para la próxima vez)
```

---

## 2. FLUJO DE APRENDIZAJE BAJO LAS 4 CAPAS DEL VEREDICTO [T2]

### 2.1 Las 4 Capas — Mapeo Exacto al Código Existente [T2]

El sistema de aprendizaje usa las 4 capas del Veredicto que YA EXISTEN en el código:

```
┌─────────────────────────────────────────────────────────────────┐
│ CAPA 1: DeterministicPipeline [T2]                              │
│ Archivo: src/core/verdict_parts/deterministic_pipeline/_core.py │
│                                                                 │
│ 7 TAREAS DETERMINÍSTICAS (sin IA):                              │
│   T1: classify_intent()     — Clasificar intención del input    │
│   T2: extract_entities()    — Extraer entidades nombradas       │
│   T3: suggest_pattern()     — Sugerir patrón de la librería     │
│   T4: fill_template_gaps()  — Rellenar gaps en templates        │
│   T5: generate_pattern()    — Generar patrón de validación      │
│   T6: explain_violation()   — Explicar violación detectada      │
│   T7: describe_subtask()    — Describir sub-tarea del DAG       │
│                                                                 │
│ + NUEVA TAREA DEL CHIP: memory_lookup()                         │
│   → Consulta LRU cache + SQLite grafo                           │
│   → Si CACHE_HIT con confidence > 0.8 → resuelve directo <5ms  │
│   → La IA NO se enciende                                        │
│                                                                 │
│ + NUEVA TAREA DEL CHIP: dag_node_adapt()                        │
│   → Si el nodo del DAG falla por campo/columna no encontrada    │
│   → Consulta mapeos aprendidos antes de propagar el error       │
│   → Si encuentra redireccionamiento → re-ejecuta el nodo        │
│   → Esto es CÓMO EL CHIP MODIFICA EL DAG FRACTAL DE 121 NODOS  │
├─────────────────────────────────────────────────────────────────┤
│ CAPA 2: EvidenceCollector [T2]                                  │
│ Archivo: src/core/verdict_parts/evidence_collector.py           │
│                                                                 │
│ Funciones existentes:                                           │
│   - collect_intent_evidence()                                    │
│   - collect_goal_evidence()                                      │
│   - collect_code_safety_evidence()                               │
│   - collect_syntax_evidence()                                    │
│   - collect_entity_evidence()                                    │
│   - collect_all_evidence()                                       │
│                                                                 │
│ + NUEVA FUNCIÓN DEL CHIP:                                       │
│   - collect_memory_chip_evidence(query) → Evidence               │
│     → Busca mapeos aprendidos en el grafo                       │
│     → Si encuentra: genera evidencia tipo CACHE_HIT (peso 1.3x) │
│     → Señales a favor: mapeo aprobado previamente               │
│     → Señales en contra: conflictos con otros mapeos            │
├─────────────────────────────────────────────────────────────────┤
│ CAPA 3: ConsensusResolver [T2]                                  │
│ Archivo: src/core/verdict_parts/consensus_resolver.py           │
│                                                                 │
│ Sistema existente:                                              │
│   - Thresholds: CERTAIN=0.85, HIGH=0.6, MEDIUM=0.3             │
│   - EVIDENCE_TYPE_WEIGHTS: CACHE_HIT tiene peso 1.3x           │
│   - resolve(evidence, question) → ConsensusResult               │
│                                                                 │
│ + NUEVA LÓGICA DEL CHIP:                                        │
│   - Si CACHE_HIT evidence presente y confidence > 0.8           │
│     → ConsensusResolver emite DETERMINISTIC_RESULT directo      │
│     → NO pasa a Capa 4 (IA no se enciende)                     │
│   - Ajuste dinámico de peso:                                    │
│     → hit_count > 20: peso sube a 1.5x (muy confiable)         │
│     → hit_count > 50: peso sube a 1.8x (altamente validado)    │
│     → mapeo revocado: peso baja a 0.0 (eliminado)              │
├─────────────────────────────────────────────────────────────────┤
│ CAPA 4: VerdictEngine [T2]                                      │
│ Archivo: src/core/verdict_parts/verdict_engine/__init__.py      │
│                                                                 │
│ Sistema existente:                                              │
│   - verdict(text, code, language, question, context)            │
│   - ask_yes_no(question, context, evidence_for, evidence_against)│
│                                                                 │
│ + INTEGRACIÓN DEL CHIP:                                         │
│   - Solo se invoca si Capa 3 no alcanza consenso                │
│   - El Chip genera la hipótesis binaria estricta                │
│   - El motor de Rust presenta la pregunta al LLM               │
│   - Qwen3-0.6B responde con UN SOLO TOKEN: SÍ o NO             │
│   - No genera texto, no propone soluciones [T1+T2]             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Cómo el Chip Modifica el DAG Fractal de 121 Nodos [T2 — GRIETA CERRADA]

El Texto 2 dice: *"El conocimiento evolutivo modifica de forma determinista la configuración del DAG Fractal de 121 nodos"*. Esto NO significa que el Chip reescriba nodos. Significa:

1. **Redireccionamiento de campos**: Cuando un nodo del DAG busca `estatus_cliente` y falla, el Chip intercepta el error, busca en el grafo de mapeos, y si existe el redireccionamiento a `estado_id`, el nodo se re-ejecuta con el campo corregido. El nodo NO cambia — su configuración se adapta dinámicamente.

2. **Enrutamiento de herramientas MCP**: Cuando el nodo de un sub-grafo invoca una herramienta MCP y el usuario usa jerga local, el Chip traduce la intención antes de la invocación. El sub-grafo no se modifica — su input se pre-procesa.

3. **Políticas de seguridad por nodo**: Cuando un nodo ejecuta una acción en zona gris, el Chip inyecta la clasificación aprendida (ej: "esto ES un gasto crítico") antes de la evaluación del Safety Gate. El nodo no cambia — su contexto de ejecución se enriquece.

**Implementación concreta** en `zenic-runtime/src/context.rs`:
- `ExecutionContext` gana un campo `memory_mappings: Arc<MemoryChip>` 
- Antes de cada ejecución de nodo, `memory_mappings.lookup()` busca adaptaciones
- Si hay CACHE_HIT → el nodo recibe parámetros adaptados
- Si no → flujo normal, y si falla → se dispara el proceso de aprendizaje

### 2.3 Las 7 Tareas Determinísticas del Chip [T2 — GRIETA CERRADA]

La Capa 1 (DeterministicPipeline) ejecuta 7 tareas sin IA. El Chip añade capacidades a estas tareas existentes:

| Tarea Original | Capacidad Nueva del Chip | Sin IA? |
|---------------|------------------------|---------|
| T1: classify_intent | Si el intent tiene sinónimo aprendido → clasificación directa | ✅ Sin IA |
| T2: extract_entities | Si una entidad tiene mapeo de campo → extracción directa | ✅ Sin IA |
| T3: suggest_pattern | Si hay mapeo de política → sugerencia directa | ✅ Sin IA |
| T4: fill_template_gaps | Si hay redireccionamiento de campo → gap filling directo | ✅ Sin IA |
| T5: generate_pattern | Patrones de validación enriquecidos con mapeos aprendidos | ✅ Sin IA |
| T6: explain_violation | Explicaciones enriquecidas con precedentes aprendidos | ✅ Sin IA |
| T7: describe_subtask | Descripciones adaptadas al contexto del tenant | ✅ Sin IA |
| **NUEVA: memory_lookup** | Busca en LRU cache + SQLite grafo → CACHE_HIT o miss | ✅ Sin IA |
| **NUEVA: dag_node_adapt** | Adapta parámetros de nodo con mapeos aprendidos | ✅ Sin IA |

### 2.4 Cierre de Circuito con HITL Obligatorio [T2 — GRIETA CERRADA]

El Texto 2 es explícito: *"Se exige de forma mandatoria una justificación del administrador y se adjunta la evidencia de ejecución recolectada"*.

**Implementación concreta** en `hitl_bridge.rs`:
```rust
struct HITLApprovalRequest {
    mapping: SemanticMapping,
    verdict: LearningVerdict,
    evidence_bundle: EvidenceBundle,     // evidencia de Capa 2
    consensus_score: f64,                // score de Capa 3
    ia_question: String,                 // la pregunta binaria exacta
    ia_response: bool,                   // SÍ/NO de Qwen3-0.6B
    
    // CAMPOS OBLIGATORIOS — el admin DEBE completarlos:
    admin_justification: Option<String>, // OBLIGATORIO: ¿Por qué aprueba?
    admin_evidence_review: Option<String>, // OBLIGATORIO: ¿Revisó la evidencia?
    risk_acknowledgment: Option<bool>,    // OBLIGATORIO: ¿Reconoce el riesgo?
}

// La aprobación FALLA si los campos obligatorios no están completos
fn approve(request_id: &str, admin_response: HITLAdminResponse) -> Result<()> {
    if admin_response.justification.is_none() || admin_response.justification.unwrap().len() < 10 {
        return Err(HITLError::JustificationRequired);
    }
    if admin_response.evidence_review.is_none() {
        return Err(HITLError::EvidenceReviewRequired);
    }
    if admin_response.risk_acknowledgment != Some(true) {
        return Err(HITLError::RiskAcknowledgmentRequired);
    }
    // ... proceder con aprobación
}
```

**Excepción AUTO_APPROVE** (solo para mapeos de baja criticidad):
- confidence > 0.9 Y hit_count > 10 Y la relación es SYNONYM_OF (no ROUTES_TO ni CLASSIFIES_AS)
- Aún así se registra en audit trail con justificación automática del sistema

---

## 3. SERIALIALIZACIÓN: rkyv + bincode [T3]

### 3.1 Principio Rector [T3]

```
┌─────────────────────────────────────────────────────────┐
│                    CAPA EXTERNA                         │
│  APIs HTTP, YAML config, logs humanos                   │
│  → serde_json (legible, compatible)                     │
├─────────────────────────────────────────────────────────┤
│                    CAPA DE TRÁNSITO                      │
│  SharedMemoryBus, DAG context, Policy hot path,         │
│  Memory Chip cache, Safety Gate config                  │
│  → rkyv (zero-copy, O(1) read, sin alocación)          │
├─────────────────────────────────────────────────────────┤
│                    CAPA DE PERSISTENCIA                  │
│  MerkleLedger, Checkpoints, TheoremCache, Audit trail,  │
│  Semantic Graph SQLite                                  │
│  → bincode + zstd (compacto, cripto-amigable)           │
└─────────────────────────────────────────────────────────┘
```

### 3.2 NodeValue: Reemplazo de serde_json::Value [T3]

El cuello de botella principal: `NodeOutput.data: HashMap<String, serde_json::Value>` en `zenic-runtime/src/context.rs`.

```rust
#[derive(Archive, Serialize, Deserialize, Clone, Debug)]
pub enum NodeValue {
    Null,
    Bool(bool),
    I64(i64),
    F64(f64),
    Str(String),
    Bytes(Vec<u8>),
    Map(Vec<(String, NodeValue)>),  // más eficiente que HashMap para rkyv
    List(Vec<NodeValue>),
}

// Compatibilidad: conversión bidireccional
impl From<serde_json::Value> for NodeValue { ... }
impl From<NodeValue> for serde_json::Value { ... }
```

### 3.3 rkyv en los Componentes Clave [T3]

| Componente | Antes | Después | Ganancia |
|-----------|-------|---------|----------|
| DAG NodeOutput | `serde_json::Value` (heap alloc + clone) | `NodeValue` + rkyv (zero-copy) | ~10x menos alloc |
| SharedMemoryBus | PyObject refs (ya zero-copy para PyO3) | + rkyv bytes para inter-Rust | O(1) field access |
| Policy Engine hot path | serde deserialize cada evaluación | rkyv archived policies | <100μs eval |
| Safety Gate config | `serde_json::Value` | `NodeValue` + rkyv | zero-copy |
| Memory Chip cache | N/A (nuevo) | rkyv LRU cache | <1μs lookup |
| ConsensusResolver weights | estáticos | dinámicos (rkyv map) | ajuste en runtime |

### 3.4 bincode en los Componentes de Persistencia [T3]

| Componente | Antes | Después | Ganancia |
|-----------|-------|---------|----------|
| MerkleLedger seal | BLAKE3(raw UTF-8) | BLAKE3(bincode bytes) | más determinista |
| TheoremCache | json.dumps/loads en SQLite | bincode via _zenic_native | ~60% menos tamaño |
| Semantic Graph | N/A (nuevo) | bincode para bulk operations | compacto |
| Learning audit trail | N/A (nuevo) | bincode + BLAKE3 | inmutable |
| Checkpoints | bincode + zstd ✅ | sin cambio | ya óptimo |

### 3.5 Cuellos de Botella Específicos a Eliminar [T3]

1. **`JSON.stringify(context)` en Policy eval cache key** (`evaluator.ts:363`)
   → Reemplazar con BLAKE3 hash del contexto serializado en bincode

2. **4x `JSON.parse()` al cargar policy de DB** (`evaluator.ts:343-358`)
   → Reemplazar con bincode deserialize desde Rust bridge

3. **`serde_json::Value` en DAG NodeOutput** (`zenic-runtime/context.rs`)
   → Reemplazar con `NodeValue` + rkyv

4. **`serde_json::Value` en Safety Engine config** (`zenic-safety/engine.rs`)
   → Reemplazar con `NodeValue` + rkyv

---

## 4. ESTRUCTURA DEL NUEVO CRATE: zenic-memory [T1+T2]

```
zenic-v2/zenic-memory/
├── Cargo.toml
├── ontology/
│   └── base-es.yaml                    # ~50 mapeos universales [T1]
└── src/
    ├── lib.rs                          # Public API
    ├── types.rs                        # SemanticMapping, LearningVerdict, etc. [T1+T2]
    ├── errors.rs                       # Error types
    ├── graph.rs                        # Semantic Graph (SQLite) [T1+T2]
    ├── ontology.rs                     # Shared Ontology Layer (opt-in) [T1]
    ├── cache.rs                        # LRU cache rkyv (hot path <1μs) [T1+T3]
    ├── hypothesis.rs                   # Hypothesis Generator [T1]
    ├── schema_drift.rs                 # Mecanismo 1: Schema Drift [T1]
    ├── intent_routing.rs               # Mecanismo 2: Intent Routing [T1]
    ├── policy_refinement.rs            # Mecanismo 3: Policy Refinement [T1]
    ├── verdict_adapter.rs              # Bridge a VerdictEngine.ask_yes_no() [T2]
    ├── dag_adapter.rs                  # Bridge al DAG Fractal (node adaptation) [T2 - GRIETA CERRADA]
    ├── hitl_bridge.rs                  # Bridge a HITL con justificación obligatoria [T2 - GRIETA CERRADA]
    ├── merkle_seal.rs                  # MerkleLedger BLAKE3 seal [T2+T3]
    ├── yaml_renderer.rs               # YAML declarativo para hot-reload [T2]
    ├── subscription_gate.rs            # Feature gates por tier [T1]
    └── lifecycle.rs                    # Learning lifecycle (Saga workflow) [T1+T2]
```

### 4.1 Tipos Core [T1+T2]

```rust
// === Del Texto 1: Chip Binario ===

struct SemanticMapping {
    id: Uuid,
    origin: String,           // ej: "estatus_cliente"
    relation: MappingRelation, // SYNONYM_OF, EQUIVALENT_TO, ROUTES_TO, CLASSIFIES_AS, OVERRIDES
    destination: String,      // ej: "estado_id"
    source: MappingSource,    // SCHEMA_DRIFT, INTENT_ROUTING, POLICY_REFINEMENT, ONTOLOGY_BASE, MANUAL
    tenant_id: TenantId,
    confidence: f64,          // 0.0-1.0, sube con cada uso exitoso
    hit_count: u32,           // veces usado exitosamente
    approved_by: Option<String>,
    admin_justification: Option<String>,  // [T2] OBLIGATORIO tras HITL
    approved_at: Option<DateTime<Utc>>,
    merkle_hash: Option<String>,
    created_at: DateTime<Utc>,
}

enum MappingRelation { SynonymOf, EquivalentTo, RoutesTo, ClassifiesAs, Overrides }
enum MappingSource { SchemaDrift, IntentRouting, PolicyRefinement, OntologyBase, ManualEntry }

// === Del Texto 2: 4 Capas del Veredicto ===

struct LearningVerdict {
    mapping: SemanticMapping,
    hypothesis: String,        // La pregunta binaria que se le hizo a la IA
    ia_response: bool,         // SÍ/NO de Qwen3-0.6B
    evidence_for: Vec<String>,
    evidence_against: Vec<String>,
    consensus_score: f64,      // Score del ConsensusResolver
}

struct EvidenceBundle {
    cache_hit: bool,           // ¿Se encontró en caché?
    existing_mappings: Vec<SemanticMapping>,  // Mapeos relacionados
    conflict_mappings: Vec<SemanticMapping>,  // Mapeos en conflicto
    source_context: String,    // Contexto del error/input que disparó el aprendizaje
}

struct HITLApprovalRequest {
    mapping: SemanticMapping,
    verdict: LearningVerdict,
    evidence_bundle: EvidenceBundle,
    consensus_score: f64,
    ia_question: String,
    ia_response: bool,
    admin_justification: Option<String>,    // OBLIGATORIO [T2]
    admin_evidence_review: Option<String>,  // OBLIGATORIO [T2]
    risk_acknowledgment: Option<bool>,      // OBLIGATORIO [T2]
}

// === Del Texto 2: Learning Lifecycle ===

enum LearningPhase {
    Detecting,               // Capa 1: Detección analítica
    MemoryLookup,            // Capa 1: Búsqueda en caché/grafo (NUEVA)
    DagNodeAdapt,            // Capa 1: Adaptación de nodo DAG (NUEVA)
    GeneratingHypotheses,    // Hipótesis estructuradas
    CollectingEvidence,      // Capa 2: EvidenceCollector
    ResolvingConsensus,      // Capa 3: ConsensusResolver
    AwaitingVerdict,         // Capa 4: VerdictEngine (IA SÍ/NO)
    AwaitingHITL,            // HITL validación humana obligatoria
    RenderingYAML,           // Compilación a YAML declarativo
    SealingMerkle,           // Sellado criptográfico BLAKE3
    CachingResult,           // Escritura en caché LRU
    Complete,                // Listo para <5ms la próxima vez
    Failed(LearningError),
    Compensating,            // Rollback (Saga compensation)
}
```

### 4.2 Schema SQLite [T1+T2+T3]

```sql
-- Tabla principal de mapeos semánticos [T1]
CREATE TABLE semantic_mappings (
    id TEXT PRIMARY KEY,
    origin TEXT NOT NULL,
    relation TEXT NOT NULL,       -- SynonymOf, EquivalentTo, RoutesTo, ClassifiesAs, Overrides
    destination TEXT NOT NULL,
    source TEXT NOT NULL,         -- SchemaDrift, IntentRouting, PolicyRefinement, OntologyBase, ManualEntry
    tenant_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    hit_count INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT,
    admin_justification TEXT,     -- [T2] Obligatorio tras HITL
    approved_at TEXT,
    merkle_hash TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(origin, relation, tenant_id)
);

-- Ontología base compartida (opt-in) [T1]
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

-- Audit trail de aprendizaje [T2+T3]
CREATE TABLE learning_audit (
    id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL,
    action TEXT NOT NULL,           -- PROPOSED, IA_APPROVED, HITL_APPROVED, HITL_REJECTED, SEALED, REVOKED
    actor TEXT NOT NULL,            -- system, ia:qwen3-0.6b, admin@email.com
    evidence_json TEXT NOT NULL,    -- bincode serializado [T3]
    consensus_score REAL,
    admin_justification TEXT,       -- [T2] Solo para HITL_APPROVED
    timestamp TEXT NOT NULL,
    FOREIGN KEY (mapping_id) REFERENCES semantic_mappings(id)
);

CREATE INDEX idx_sm_origin ON semantic_mappings(origin, tenant_id);
CREATE INDEX idx_sm_destination ON semantic_mappings(destination, tenant_id);
CREATE INDEX idx_sm_source ON semantic_mappings(source, tenant_id);
CREATE INDEX idx_la_mapping ON learning_audit(mapping_id);
CREATE INDEX idx_la_action ON learning_audit(action, timestamp);
```

---

## 5. FASES DE IMPLEMENTACIÓN

### FASE 1: Fundación — zenic-memory + rkyv infra [T1+T2+T3]

**1A.** Crear crate `zenic-memory` con: lib.rs, types.rs, errors.rs, graph.rs, ontology.rs, cache.rs
**1B.** Agregar `rkyv = "0.8"` al workspace Cargo.toml [T3]
**1C.** Agregar `#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]` a tipos en zenic-proto [T3]
**1D.** Crear `NodeValue` reemplazando `serde_json::Value` en zenic-runtime [T3]
**1E.** Crear ontología base YAML (`base-es.yaml`) con ~50 mapeos [T1]
**1F.** Agregar `encode_rkyv()` / `decode_rkyv()` en zenic-proto [T3]

**Archivos nuevos**: 7 Rust + 1 YAML
**Archivos modificados**: zenic-v2/Cargo.toml, zenic-proto/src/{ids,domain,serde_}.rs, zenic-runtime/src/context.rs

**Criterio de Aceptación**:
- `cargo build -p zenic-memory` compila
- `cargo build -p zenic-runtime` compila con NodeValue
- LRU cache lookup <1ms con rkyv
- Ontología base carga desde YAML embebido

---

### FASE 2: 3 Mecanismos + rkyv Hot Path [T1+T3]

**2A.** Implementar `hypothesis.rs` — Generador de hipótesis compartido [T1]
**2B.** Implementar `schema_drift.rs` — Mecanismo 1 [T1]
**2C.** Implementar `intent_routing.rs` — Mecanismo 2 [T1]
**2D.** Implementar `policy_refinement.rs` — Mecanismo 3 [T1]
**2E.** Agregar `evaluate_rkyv()` en zenic-policy [T3]
**2F.** Reemplazar `serde_json::Value` con `NodeValue` en zenic-safety [T3]
**2G.** Eliminar `JSON.stringify(context)` en evaluator.ts → BLAKE3 hash [T3]

**Archivos nuevos**: 4 Rust
**Archivos modificados**: zenic-policy/src/engine.rs, zenic-safety/src/engine.rs, gateway/policy-engine/evaluator.ts

**Criterio de Aceptación**:
- 3 mecanismos generan hipótesis binarias correctas
- Policy eval <100μs con rkyv
- Cache key <5μs con BLAKE3

---

### FASE 3: Integración Verdict Pipeline + PyO3 Bridge [T2+T3]

**3A.** Implementar `verdict_adapter.rs` — Bridge a VerdictEngine.ask_yes_no() [T2]
**3B.** Implementar `dag_adapter.rs` — Bridge al DAG Fractal (adaptación de nodos) [T2 — GRIETA CERRADA]
**3C.** Implementar `memory_chip.rs` en zenic-pybridge — PyO3 bridge [T3]
**3D.** Modificar `evidence_collector.py` — `collect_memory_chip_evidence()` [T2]
**3E.** Modificar `verdict_engine/__init__.py` — Memory Chip pre-check + CACHE_HIT bypass [T2]
**3F.** Modificar `consensus_resolver.py` — Pesos dinámicos del Chip [T2]
**3G.** Modificar `deterministic_pipeline/_core.py` — Tareas memory_lookup + dag_node_adapt [T2 — GRIETA CERRADA]
**3H.** SharedMemoryBus rkyv support en bus.rs [T3]

**Archivos nuevos**: 2 Rust (verdict_adapter.rs, dag_adapter.rs, memory_chip.rs)
**Archivos modificados**: 4 Python, 1 Rust (bus.rs)

**Criterio de Aceptación**:
- Flujo end-to-end: error → hipótesis → veredicto IA → HITL → sellado
- CACHE_HIT bypass funciona (<5ms) [T2]
- DAG node adaptation funciona (nodo fallido → mapeo → re-ejecución) [T2]
- PyO3 bridge compila y Python llama a Rust

---

### FASE 4: Cierre de Circuito — HITL + Merkle + YAML + Lifecycle [T2+T3]

**4A.** Implementar `hitl_bridge.rs` — Con justificación OBLIGATORIA del admin [T2 — GRIETA CERRADA]
**4B.** Implementar `merkle_seal.rs` — bincode → BLAKE3 → MerkleLedger commit [T2+T3]
**4C.** Implementar `yaml_renderer.rs` — YAML declarativo para PolicyHotReloader [T2]
**4D.** Implementar `lifecycle.rs` — Learning lifecycle como WorkflowDefinition con Saga [T1+T2]
**4E.** Migrar TheoremCache a bincode via _zenic_native [T3]

**Archivos nuevos**: 4 Rust
**Archivos modificados**: 1 Python (theorem_cache), 1 Rust (_zenic_native/lib.rs)

**Criterio de Aceptación**:
- HITL approval REQUIERE justificación (falla sin ella) [T2]
- MerkleLedger sella con BLAKE3(bincode bytes) [T2+T3]
- YAML se renderiza y PolicyHotReloader lo detecta (30s) [T2]
- LearningWorkflow completa ciclo con Saga compensation [T2]
- TheoremCache usa bincode [T3]

---

### FASE 5: Subscription Gates + API Routes + TS↔Rust Bridge [T1+T3]

**5A.** Implementar `subscription_gate.rs` — Feature gates por tier [T1]
```
Starter:     Schema Drift (10 mapeos/mes, LRU 100)
Business:    Schema Drift + Intent Routing (50 mapeos/mes, LRU 500)
Enterprise:  Los 3 mecanismos + Ontología (ilimitado, LRU 2000)
On-Premise:  Los 3 + Ontología + Export/Import + Custom (ilimitado)
```

**5B.** 9 API Routes (TypeScript) [T1]
**5C.** Bridge TS↔Rust Policy Engine (YAML → bincode → Rust) [T3]
**5D.** Actualizar zenic-subscription con nuevos feature gates y usage types [T1]

**Archivos nuevos**: 9 TypeScript + 1 Rust
**Archivos modificados**: 2 TypeScript, 2 Rust (subscription)

**Criterio de Aceptación**:
- Feature gates bloquean mecanismos según tier
- API routes responden correctamente
- TS→Rust policy bridge funciona con bincode
- Test end-to-end por tier

---

## 6. MATRIZ DE TRAZABILIDAD COMPLETA

### Texto 1: Chip de Memoria Adaptativa Binaria

| # | Requisito | Fase | Archivo | Estado |
|---|-----------|------|---------|--------|
| T1-1 | Principio: Capa Propone, IA Clasifica, Humano Valida | Todas | types.rs, lifecycle.rs | ✅ |
| T1-2 | Grafo de Mapeo Semántico (SQLite) | F1 | graph.rs | ✅ |
| T1-3 | Registros Origen→Relación→Destino | F1 | types.rs (SemanticMapping) | ✅ |
| T1-4 | Mecanismo 1: Schema Drift | F2 | schema_drift.rs | ✅ |
| T1-5 | Mecanismo 2: Intent Routing | F2 | intent_routing.rs | ✅ |
| T1-6 | Mecanismo 3: Policy Refinement | F2 | policy_refinement.rs | ✅ |
| T1-7 | Ejemplo estatus_cliente→estado_id | F2 | schema_drift.rs | ✅ |
| T1-8 | Ejemplo "tumba la cuenta" | F2 | intent_routing.rs | ✅ |
| T1-9 | Ejemplo "reparación urgente" | F2 | policy_refinement.rs | ✅ |
| T1-10 | Diagrama flujo caché→hipótesis→IA→HITL→grafo | F3-F4 | lifecycle.rs | ✅ |
| T1-11 | Caché local junto a Rust/Python | F1 | cache.rs | ✅ |
| T1-12 | IA solo 1 token SÍ/NO | F3 | verdict_adapter.rs | ✅ |
| T1-13 | Registro inmutable MerkleLedger | F4 | merkle_seal.rs | ✅ |
| T1-14 | Grafo híbrido (tenant + ontología) | F1 | ontology.rs + graph.rs | ✅ |
| T1-15 | Latencia <5ms Gateway | F3 | CACHE_HIT bypass | ✅ |

### Texto 2: Flujo de Aprendizaje bajo las 4 Capas del Veredicto

| # | Requisito | Fase | Archivo | Estado |
|---|-----------|------|---------|--------|
| T2-1 | Offline, CPU-only, ARM64, 500MB RAM | Todas | Principio invariable | ✅ |
| T2-2 | Qwen3-0.6B modelo local | F3 | verdict_adapter.rs | ✅ |
| T2-3 | Invariante 1+2: LLM NUNCA genera contenido | F3 | verdict_adapter.rs | ✅ |
| T2-4 | Tecnología descartada (vectoriales, Neo4j, etc.) | Todas | SQLite + YAML local | ✅ |
| T2-5 | Memoria NO altera pesos del LLM | Todas | Principio invariable | ✅ |
| T2-6 | **Memoria modifica DAG Fractal 121 nodos** | F3 | **dag_adapter.rs** | ✅ CERRADO |
| T2-7 | Componente 1: Persistencia SQLite | F1 | graph.rs | ✅ |
| T2-8 | Componente 2: YAML Declarativo Hot-Reload | F4 | yaml_renderer.rs | ✅ |
| T2-9 | **Capa 1: 7 tareas determinísticas + memory_lookup + dag_node_adapt** | F3 | **deterministic_pipeline/_core.py** | ✅ CERRADO |
| T2-10 | Capa 2: EvidenceCollector + memory_chip_evidence | F3 | evidence_collector.py | ✅ |
| T2-11 | Capa 3: ConsensusResolver + pesos dinámicos | F3 | consensus_resolver.py | ✅ |
| T2-12 | Capa 4: VerdictEngine (solo empates) | F3 | verdict_adapter.rs | ✅ |
| T2-13 | **HITL obligatorio con justificación del admin** | F4 | **hitl_bridge.rs** | ✅ CERRADO |
| T2-14 | Python renderiza YAML | F4 | yaml_renderer.rs | ✅ |
| T2-15 | zenic-policy hot-reload seguro | F4 | yaml_renderer.rs + PolicyHotReloader | ✅ |
| T2-16 | Sellado MerkleLedger BLAKE3 vía _zenic_native | F4 | merkle_seal.rs | ✅ |
| T2-17 | Resultado: próxima vez Capa 1, <5ms, sin IA | F3-F4 | CACHE_HIT + lifecycle | ✅ |

### Texto 3: Serialización rkyv + bincode

| # | Requisito | Fase | Archivo | Estado |
|---|-----------|------|---------|--------|
| T3-1 | Confirmar bincode NO está (solo en zenic-proto) | F1 | Análisis verificado | ✅ |
| T3-2 | Confirmar rkyv NO está | F1 | Análisis verificado | ✅ |
| T3-3 | Cuello de botella: serde_json en SharedMemoryBus | F3 | bus.rs enhancement | ✅ |
| T3-4 | bincode: persistencia MerkleLedger | F4 | merkle_seal.rs | ✅ |
| T3-5 | bincode: transmisión red entre nodos Rust | F5 | TS↔Rust bridge | ✅ |
| T3-6 | bincode: limitación (requiere deserialización) | Todas | Reconocido | ✅ |
| T3-7 | rkyv: SharedMemoryBus zero-copy | F3 | bus.rs + rkyv | ✅ |
| T3-8 | rkyv: Policy Engine hot path | F2 | evaluate_rkyv() | ✅ |
| T3-9 | rkyv: DAG Core context (is_approved O(1)) | F1 | NodeValue + rkyv | ✅ |
| T3-10 | rkyv: Safety Gate microsegundos | F2 | validate_rkyv() | ✅ |
| T3-11 | Veredicto: rkyv tránsito + bincode storage | Todas | Principio rector | ✅ |
| T3-12 | serde_json solo APIs externas | Todas | Principio rector | ✅ |
| T3-13 | bincode para TheoremCache | F4 | _zenic_native | ✅ |
| T3-14 | Eliminar JSON.stringify en cache key | F2 | evaluator.ts | ✅ |
| T3-15 | Eliminar JSON.parse en policy DB load | F5 | TS↔Rust bridge | ✅ |

---

## 7. RESUMEN DE ARCHIVOS

### Nuevos: 20 Rust + 9 TypeScript + 1 YAML = 30 archivos

### Modificados: 8 Rust + 4 Python + 2 TypeScript = 14 archivos

### Total: 44 archivos, ~5,500 LOC estimadas

| Lenguaje | LOC |
|----------|-----|
| Rust | ~4,600 |
| Python | ~350 |
| TypeScript | ~500 |
| YAML | ~50 |
| **Total** | **~5,500** |

---

*Plan Definitivo v2 — Zenic-Agents v3.0.0 — 3 Textos Integrados, 0 Grietas*
