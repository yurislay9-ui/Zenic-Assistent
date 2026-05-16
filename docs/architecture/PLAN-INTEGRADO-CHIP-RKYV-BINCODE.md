# PLAN INTEGRADO — Chip Binario + 4 Capas Veredicto + rkyv/bincode
## Zenic-Agents v3.0.0 — Blueprint Unificado

---

## Respuesta a la Pregunta del Texto 3

**¿Qué volumen de datos o nivel de anidamiento tendrán los contextos de petición?**

Análisis del código existente (`zenic-runtime/src/context.rs`):

```
ExecutionContext:
├── execution_id: UUID (16 bytes)
├── session_id: UUID (16 bytes)
├── tenant_id: UUID (16 bytes)
├── started_at: Instant (8 bytes)
└── node_outputs: HashMap<NodeId, NodeOutput>
    └── NodeOutput:
        ├── source_node_id: UUID
        ├── success: bool
        ├── error_message: Option<String>
        └── data: HashMap<String, serde_json::Value>  ← EL CUELLO DE BOTELLA
            └── JSON Value tree (5-10 keys por nodo)
```

**Estimación real por ejecución típica del DAG (20 nodos)**:

| Métrica | serde_json (actual) | rkyv zero-copy | bincode |
|---------|-------------------|----------------|---------|
| Tamaño contexto completo | ~10-50 KB | ~3-15 KB | ~5-20 KB |
| Nivel de anidamiento máximo | 4-6 niveles | Igual (estructura) | Igual |
| Tiempo serialización | ~200-500μs | ~50μs (write only) | ~100-200μs |
| Tiempo deserialización | ~200-500μs | **0μs (zero-copy)** | ~100-200μs |
| Alocaciones memoria | 50-200 heap allocs | **0 allocs** | 50-200 heap allocs |

**Conclusión**: Los payloads son de tamaño moderado (10-50KB) pero con anidamiento significativo (4-6 niveles). El impacto principal no es el tamaño sino la **frecuencia**: cada nodo del DAG genera un `serde_json::Value` que se clona en cada paso. Con rkyv, se elimina toda alocación en el hot path.

---

## Estado Actual de la Serialización (Hallazgos del Análisis)

### ✅ Lo que ya funciona bien
| Componente | Formato | Eficiencia |
|-----------|---------|-----------|
| zenic-flow checkpoints | bincode + zstd | ✅ Óptimo |
| SharedMemoryBus | PyObject refs (zero-copy) | ✅ Óptimo para PyO3 |
| PyO3 classes (SafetyGate, Niche) | Zero-copy getters | ✅ Óptimo |
| MerkleLedger hashing | BLAKE3(raw bytes) | ✅ Óptimo |
| Crypto/Hash functions | Raw bytes → String | ✅ Óptimo |

### 🔴 Cuellos de botella reales
| Componente | Problema | Impacto |
|-----------|----------|---------|
| DAG NodeOutput.data | `HashMap<String, serde_json::Value>` | Heap alloc + clone en cada nodo |
| Policy eval cache key | `JSON.stringify(context)` | Stringify en cada evaluación |
| Policy DB load | 4x `JSON.parse()` por policy miss | Parse en cada cache miss |
| zenic-safety config | `serde_json::Value` en Rust | Parse en cada validación |
| TheoremCache storage | `json.dumps/loads` en SQLite | Serialize en cada save/lookup |
| Gap TS↔Rust Policy Engine | Sin puente de datos | Dos motores independientes |

### 🟡 No es cuello de botella pero se puede mejorar
| Componente | Formato actual | Mejora propuesta |
|-----------|---------------|-----------------|
| Session serialization | serde (bincode vía zenic-proto) | Ya es eficiente |
| License verify | serde_json parse | Frio, no crítico |
| Forensic metadata | JSON string param | Frio, no crítico |

---

## Plan Unificado: 3 Textos Integrados

### Principio Rector

> **rkyv** para todo lo que vive en memoria y se lee frecuentemente (hot path).
> **bincode** para todo lo que se persiste a disco (cold storage).
> **serde_json** SOLO para APIs externas y YAML rendering (interfaz humana).

### Arquitectura de Serialización Propuesta

```
┌─────────────────────────────────────────────────────────┐
│                    CAPA EXTERNA                         │
│  APIs HTTP, YAML config, logs humanos                   │
│  → serde_json (legible, compatible)                     │
├─────────────────────────────────────────────────────────┤
│                    CAPA DE TRÁNSITO                      │
│  SharedMemoryBus, DAG context, Policy hot path          │
│  → rkyv (zero-copy, O(1) read, sin alocación)          │
├─────────────────────────────────────────────────────────┤
│                    CAPA DE PERSISTENCIA                  │
│  MerkleLedger, Checkpoints, TheoremCache, Audit trail   │
│  → bincode + zstd (compacto, cripto-amigable)           │
└─────────────────────────────────────────────────────────┘
```

---

## FASES DE IMPLEMENTACIÓN (Integradas)

### FASE 1: Fundación — zenic-memory crate + rkyv/bincode infra
**Objetivo**: Crear el crate base + actualizar la infra de serialización

**1A. Nuevo crate `zenic-memory`** (del Plan del Texto 1+2):
```
zenic-v2/zenic-memory/
├── Cargo.toml
└── src/
    ├── lib.rs
    ├── types.rs          # SemanticMapping, LearningVerdict, MemoryQuery, MemoryLookupResult
    ├── errors.rs
    ├── graph.rs          # Semantic Graph Engine (SQLite-backed)
    ├── ontology.rs       # Shared Ontology Layer
    └── cache.rs          # Hot-path LRU cache
```

**1B. Agregar rkyv al workspace** (`zenic-v2/Cargo.toml`):
```toml
[workspace.dependencies]
rkyv = { version = "0.8", features = ["validation", "bytecheck"] }
rkyv_derive = "0.8"
```

**1C. Migrar tipos core a rkyv** (`zenic-proto/src/`):
- Agregar `#[derive(rkyv::Archive, rkyv::Serialize, rkyv::Deserialize)]` a:
  - `ExecutionId`, `SessionId`, `TenantId`, `WorkflowId`, `NodeId`
  - `LoadPolicy`, `BusinessDomain`, `NodeCriticality`
- Mantener `serde` para compatibilidad hacia atrás
- `zenic-proto::encode()` ahora ofrece dos variantes:
  - `encode_bincode()` — persistencia (reemplaza actual)
  - `encode_rkyv()` — tránsito (nuevo)

**1D. Migrar DAG NodeOutput** (`zenic-runtime/src/context.rs`):
- Reemplazar `HashMap<String, serde_json::Value>` con tipo propio:
  ```rust
  #[derive(Archive, Serialize, Deserialize)]
  pub struct NodeData {
      fields: HashMap<String, NodeValue>,
  }

  #[derive(Archive, Serialize, Deserialize)]
  pub enum NodeValue {
      Null,
      Bool(bool),
      I64(i64),
      F64(f64),
      Str(String),
      Bytes(Vec<u8>),
      Map(Vec<(String, NodeValue)>),
      List(Vec<NodeValue>),
  }
  ```
- `NodeValue` reemplaza `serde_json::Value` en todo el DAG runtime
- rkyv permite leer cualquier campo en O(1) sin deserializar el árbol completo
- Se mantiene compatibilidad: `From<serde_json::Value> for NodeValue` y viceversa

**1E. Actualizar zenic-flow** (`zenic-v2/zenic-flow/src/`):
- Checkpoints ya usan bincode + zstd ✅
- Agregar opción rkyv para in-memory checkpoint restoration (zero-copy resume)

**Criterio de Aceptación FASE 1**:
- `cargo build -p zenic-memory` compila
- `cargo build -p zenic-proto` compila con rkyv derives
- `cargo build -p zenic-runtime` compila con NodeValue
- Benchmarks: NodeValue rkyv access <1μs vs serde_json::Value clone ~10μs
- LRU cache lookup <1ms con rkyv zero-copy

---

### FASE 2: Mecanismos de Aprendizaje + rkyv en Hot Path
**Depende de**: FASE 1

**2A. Mecanismos del Chip** (del Plan del Texto 1+2):
```
zenic-v2/zenic-memory/src/
    ├── hypothesis.rs          # Generador de hipótesis (compartido)
    ├── schema_drift.rs        # Mecanismo 1
    ├── intent_routing.rs      # Mecanismo 2
    └── policy_refinement.rs   # Mecanismo 3
```

Todos los tipos internos usan `rkyv::Archive` para zero-copy en el hot path:
- `Hypothesis` — rkyv-archived para lookup sin deserialización
- `LearningVerdict` — rkyv-archived para pasar entre Rust ↔ Python sin copia
- `SemanticMapping` — rkyv-archived para cache lookup O(1)

**2B. Policy Engine rkyv hot path** (`zenic-policy/src/`):
- Agregar `rkyv::Archive` a `PolicyRule`, `Role`, `Permission`, `SafetyVeto`
- Nueva función `PolicyEngine::evaluate_rkyv()`:
  - Carga políticas pre-compiladas (rkyv bytes) desde memoria compartida
  - Evalúa sin deserializar — acceso directo a campos archived
  - Target: <100μs para evaluación completa de policy chain

**2C. Safety Engine rkyv** (`zenic-safety/src/`):
- Reemplazar `serde_json::Value` en config con `NodeValue` (rkyv-compatible)
- `DomainSafetyGate::validate_rkyv()` — zero-copy config access

**2D. Eliminar JSON.stringify en Policy eval cache** (`gateway/policy-engine/evaluator.ts`):
- Reemplazar cache key de `JSON.stringify(context)` a BLAKE3 hash del contexto
- Reducción estimada: de ~50μs a ~5μs por cache key computation

**Criterio de Aceptación FASE 2**:
- 3 mecanismos generan hipótesis correctas
- Policy Engine evalúa en <100μs con rkyv (vs ~500μs con serde_json)
- Cache key computation <5μs
- Hypothesis lookup zero-copy verificado con benchmarks

---

### FASE 3: Verdict Pipeline Integration + PyO3 rkyv Bridge
**Depende de**: FASE 2

**3A. VerdictAdapter** (`zenic-memory/src/verdict_adapter.rs`):
- Bridge entre Memory Chip hypotheses y VerdictEngine.ask_yes_no()
- Formatea preguntas binarias estrictas
- Procesa respuestas SÍ/NO → LearningVerdict

**3B. PyO3 rkyv Bridge** (`zenic-pybridge/src/memory_chip.rs`):
- Expone operaciones del Memory Chip a Python
- **Patrón clave**: Rust escribe rkyv bytes → SharedMemoryBus → Python lee via PyObject
- Para lookup: Python pasa query → Rust busca en cache (rkyv zero-copy) → devuelve resultado
- Sin JSON intermediario

**3C. Evidence injection** (`src/core/verdict_parts/evidence_collector.py`):
- Nuevo método `collect_memory_chip_evidence()`
- Inyecta evidencia `CACHE_HIT` cuando el Chip encuentra mapeo aprendido
- ConsensusResolver resuelve sin invocar LLM si confidence > 0.8

**3D. VerdictEngine pre-check** (`src/core/verdict_parts/verdict_engine/__init__.py`):
- Antes del pipeline completo: consultar Memory Chip
- Si CACHE_HIT con confidence > 0.8 → retornar directamente (<5ms)
- Si no → flujo normal con hipótesis del Chip alimentando el pipeline

**3E. SharedMemoryBus enhancement** (`zenic-pybridge/src/bus.rs`):
- Agregar soporte para rkyv-archived payloads
- Nuevo método: `publish_rkyv<T: Archive>(&self, topic: &str, data: &T)`
- Los subscribers pueden leer campos específicos sin deserializar todo
- Mantiene compatibilidad con PyObject actual

**Criterio de Aceptación FASE 3**:
- Flujo end-to-end: error → hipótesis → veredicto IA → HITL → sellado
- CACHE_HIT bypass funciona (<5ms)
- PyO3 bridge compila y Python llama a Rust
- SharedMemoryBus soporta rkyv payloads

---

### FASE 4: Cierre de Circuito — HITL + MerkleLedger + YAML
**Depende de**: FASE 3

**4A. HITL Bridge** (`zenic-memory/src/hitl_bridge.rs`):
- Crear ApprovalRequest cuando IA responde SÍ
- Modo SINGLE para mapeos normales
- Modo AUTO_APPROVE para mapeos con confidence > 0.9 y hit_count > 10

**4B. MerkleLedger Seal** (`zenic-memory/src/merkle_seal.rs`):
- bincode serialización del SemanticMapping → BLAKE3 hash → commit al ledger
- Anti-tampering: cualquier modificación invalida el hash

**4C. YAML Renderer** (`zenic-memory/src/yaml_renderer.rs`):
- Convierte SemanticMapping aprobado a YAML declarativo
- Formato compatible con PolicyHotReloader existente
- Escribir al directorio de políticas → hot-reload automático (30s)

**4D. Learning Lifecycle** (`zenic-memory/src/lifecycle.rs`):
- Ciclo completo como WorkflowDefinition con Saga compensation
- Steps: Detect → Hypothesize → Evidence → Consensus → Verdict → HITL → Render → Seal → Cache
- Si HITL rechaza → compensation: eliminar mapeo propuesto + rollback YAML
- Si MerkleLedger falla → compensation: rollback del YAML

**4E. bincode para TheoremCache** (`src/core/level8_theorem_cache/`):
- Reemplazar `json.dumps/loads` con bincode via _zenic_native
- Nueva función en native: `theorem_cache_serialize/deserialize`
- Reducción estimada: ~60% menos tamaño, ~3x más rápido

**Criterio de Aceptación FASE 4**:
- HITL approval funciona end-to-end
- MerkleLedger sella cada aprendizaje (bincode → BLAKE3)
- YAML se renderiza y PolicyHotReloader lo detecta
- LearningWorkflow completa ciclo con compensation
- TheoremCache usa bincode

---

### FASE 5: Subscription Gates + API Routes + Bridge TS↔Rust Policy
**Depende de**: FASE 4

**5A. Subscription Feature Gates** (`zenic-memory/src/subscription_gate.rs`):
```
Starter:     Schema Drift (10 mapeos/mes, LRU 100)
Business:    Schema Drift + Intent Routing (50 mapeos/mes, LRU 500)
Enterprise:  Los 3 mecanismos + Ontología (ilimitado, LRU 2000)
On-Premise:  Los 3 + Ontología + Export/Import + Custom (ilimitado)
```

**5B. API Routes** (9 endpoints):
- `POST /api/v1/memory/lookup` — Buscar mapeo
- `POST /api/v1/memory/hypothesize` — Generar hipótesis
- `GET  /api/v1/memory/mappings` — Listar mapeos
- `POST /api/v1/memory/approve/[id]` — HITL approve
- `POST /api/v1/memory/reject/[id]` — HITL reject
- `DELETE /api/v1/memory/mappings/[id]` — Revocar
- `GET  /api/v1/memory/ontology` — Ver ontología base
- `POST /api/v1/memory/ontology/opt-in` — Opt-in
- `GET  /api/v1/memory/stats` — Estadísticas

**5C. Bridge TS↔Rust Policy Engine**:
- El gateway TS compila YAML → bincode bytes → Rust PolicyEngine.consume_bincode()
- Elimina la duplicación de motores de políticas
- Policy eval cache usa BLAKE3 hash en vez de JSON.stringify

**5D. Actualizar zenic-subscription**:
- Nuevos feature gates: `memory_chip_basic`, `memory_chip_advanced`, `memory_chip_ontology`, `memory_chip_export`
- Nuevos usage types: `MEMORY_LOOKUPS`, `MEMORY_HYPOTHESES`, `MEMORY_MAPPINGS`

**Criterio de Aceptación FASE 5**:
- Feature gates bloquean por tier
- API routes responden
- TS→Rust policy bridge funciona
- Test end-to-end por tier

---

## Resumen: Migración de Serialización

| Componente | Antes (actual) | Después (este plan) | Ganancia estimada |
|-----------|---------------|---------------------|------------------|
| DAG NodeOutput | `serde_json::Value` | `NodeValue` + rkyv | **~10x menos alloc, ~5x más rápido** |
| Policy eval cache key | `JSON.stringify(ctx)` | BLAKE3 hash | **~10x más rápido** |
| Policy DB load | 4x `JSON.parse()` | bincode deserialize | **~3x más rápido** |
| Safety config | `serde_json::Value` | `NodeValue` + rkyv | **Zero-copy access** |
| Memory Chip cache | N/A (nuevo) | rkyv LRU | **<1μs lookup** |
| SharedMemoryBus payloads | PyObject refs | PyObject refs + rkyv bytes | **O(1) field access** |
| TheoremCache storage | JSON en SQLite | bincode en SQLite | **~60% menos tamaño, ~3x más rápido** |
| Checkpoints | bincode + zstd | bincode + zstd ✅ | Sin cambio (ya óptimo) |
| MerkleLedger seal | BLAKE3(raw UTF8) | BLAKE3(bincode bytes) | **Más determinista, más compacto** |
| Learning audit | N/A (nuevo) | bincode + BLAKE3 | **Inmutable, compacto** |

---

## Archivos Nuevos Totales

### Rust (zenic-memory crate) — 17 archivos
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

### Rust (modificados) — 8 archivos
```
zenic-v2/Cargo.toml                     # rkyv + zenic-memory al workspace
zenic-v2/zenic-proto/src/ids.rs         # Agregar rkyv derives
zenic-v2/zenic-proto/src/domain.rs      # Agregar rkyv derives
zenic-v2/zenic-proto/src/serde_.rs      # Agregar encode_rkyv()/decode_rkyv()
zenic-v2/zenic-runtime/src/context.rs   # NodeValue reemplaza serde_json::Value
zenic-v2/zenic-policy/src/engine.rs     # evaluate_rkyv() + rkyv derives
zenic-v2/zenic-safety/src/engine.rs     # NodeValue reemplaza serde_json::Value
zenic-v2/zenic-pybridge/src/lib.rs      # Agregar módulo memory_chip
```

### Rust (nuevos PyO3) — 2 archivos
```
zenic-v2/zenic-pybridge/src/memory_chip.rs
zenic-v2/zenic-memory/ontology/base-es.yaml
```

### Python (modificados) — 4 archivos
```
src/core/verdict_parts/evidence_collector.py
src/core/verdict_parts/verdict_engine/__init__.py
src/core/verdict_parts/consensus_resolver.py
src/core/level8_theorem_cache/cache.py
```

### TypeScript (nuevos API routes) — 9 archivos
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

### TypeScript (modificados) — 2 archivos
```
gateway/policy-engine/evaluator.ts      # BLAKE3 cache key + Rust bridge
gateway/mcp-gateway/engine/gateway-engine.ts  # Memory Chip integration
```

---

## Estimación de Líneas de Código

| Fase | Rust | Python | TypeScript | YAML | Total |
|------|------|--------|------------|------|-------|
| Fase 1 | ~1,800 | 0 | 0 | ~50 | ~1,850 |
| Fase 2 | ~1,200 | 0 | ~50 | 0 | ~1,250 |
| Fase 3 | ~500 | ~200 | 0 | 0 | ~700 |
| Fase 4 | ~700 | ~100 | 0 | 0 | ~800 |
| Fase 5 | ~250 | 0 | ~450 | 0 | ~700 |
| **Total** | **~4,450** | **~300** | **~500** | **~50** | **~5,300** |

---

*Plan integrado generado como parte de Zenic-Agents v3.0.0 — Implementation Blueprint*
