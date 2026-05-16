//! DAG Adapter — Middleware de interceptación para el DAG Fractal. [GRIETA 1 CERRADA]
//!
//! El "Chip" funciona como middleware de interceptación. El DAG de 121 nodos
//! es **inmutable en su topología** — no se crean ni destruyen nodos al vuelo.
//! Pero sus **parámetros de entrada/salida son flexibles**.
//!
//! Flujo de Intercepción:
//! 1. El nodo 45 (ej: extract_invoice_data) se ejecuta normalmente
//! 2. FALLA o retorna confianza baja porque el usuario dijo "cobro" en lugar de "factura"
//! 3. El dag_adapter PAUSA la ejecución del nodo
//! 4. Consulta la tabla de memoria en SQLite: ¿Existe un mapeo "cobro = factura"?
//! 5. Si EXISTE y fue previamente aprobado → inyecta el parámetro corregido en el payload
//! 6. RE-EJECUTA el nodo al instante con el parámetro adaptado
//! 7. Si NO EXISTE → dispara el flujo de aprendizaje (Capas 2→3→4)

use std::collections::HashMap;
use std::sync::Arc;

use zenic_proto::NodeId;

use crate::cache::MemoryCache;
use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::types::{NodeValue, SemanticMapping};

// ---------------------------------------------------------------------------
// DagAdapterError
// ---------------------------------------------------------------------------

/// Errors specific to DAG adapter operations.
#[derive(Debug)]
pub enum DagAdapterError {
    /// The node failed and no mapping was found to adapt it.
    NoMappingFound {
        node_id: NodeId,
        failed_field: String,
    },
    /// The adapted node also failed after re-execution.
    AdaptationFailed {
        node_id: NodeId,
        reason: String,
    },
    /// An underlying storage error occurred.
    Storage(MemoryError),
}

impl std::fmt::Display for DagAdapterError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NoMappingFound { node_id, failed_field } => {
                write!(f, "DagAdapter: no mapping found for node {} field '{}'", node_id, failed_field)
            }
            Self::AdaptationFailed { node_id, reason } => {
                write!(f, "DagAdapter: adaptation failed for node {}: {}", node_id, reason)
            }
            Self::Storage(err) => write!(f, "DagAdapter: storage error: {}", err),
        }
    }
}

impl std::error::Error for DagAdapterError {}

impl From<MemoryError> for DagAdapterError {
    fn from(err: MemoryError) -> Self {
        Self::Storage(err)
    }
}

// ---------------------------------------------------------------------------
// AdaptResult
// ---------------------------------------------------------------------------

/// Result of a DAG node adaptation attempt.
#[derive(Debug)]
pub enum AdaptResult {
    /// Adaptation succeeded — the node can be re-executed with corrected data.
    Adapted {
        /// The corrected data to inject into the node.
        corrected_data: HashMap<String, NodeValue>,
        /// The mapping that was applied.
        mapping: SemanticMapping,
    },
    /// No mapping found — learning flow should be triggered (Layers 2→3→4).
    NoMapping {
        /// The field that caused the failure.
        failed_field: String,
    },
}

// ---------------------------------------------------------------------------
// DagAdapter
// ---------------------------------------------------------------------------

/// Middleware de interceptación para el DAG Fractal.
///
/// No modifica la topología del DAG. Intercepta nodos que fallan,
/// busca mapeos aprendidos en el grafo de memoria, y re-ejecuta
/// con parámetros adaptados.
pub struct DagAdapter {
    /// Reference to the semantic graph for SQLite lookups.
    graph: Arc<SemanticGraph>,
    /// Reference to the LRU cache for hot-path lookups (<1μs).
    cache: Arc<MemoryCache>,
}

impl DagAdapter {
    /// Creates a new DAG adapter with shared references to the graph and cache.
    pub fn new(graph: Arc<SemanticGraph>, cache: Arc<MemoryCache>) -> Self {
        Self { graph, cache }
    }

    /// Intercepta un nodo fallido y busca adaptación en memoria.
    ///
    /// Flujo:
    /// 1. Extrae el campo/recurso que causó el fallo del error_message
    /// 2. Busca en caché LRU primero (<1μs)
    /// 3. Si no está en caché → busca en SQLite (<2ms)
    /// 4. Si encontrado → inyecta parámetro corregido y retorna Adapted
    /// 5. Si no encontrado → retorna NoMapping (dispara flujo de aprendizaje)
    pub fn try_adapt(
        &self,
        failed_node_id: &NodeId,
        error_message: &str,
        original_data: &HashMap<String, NodeValue>,
        tenant_id: &str,
    ) -> Result<AdaptResult, DagAdapterError> {
        // Step 1: Extract the failed field from the error message
        let failed_field = self.extract_failed_field(error_message);

        // Step 2: Check LRU cache first (<1μs)
        if let Some(mapping) = self.cache.lookup(&failed_field, tenant_id) {
            if mapping.approved {
                let corrected_data = self.inject_mapping(original_data, &mapping);
                tracing::debug!(
                    node_id = %failed_node_id,
                    field = %failed_field,
                    destination = %mapping.destination,
                    "DagAdapter: cache hit, injecting corrected parameter"
                );
                return Ok(AdaptResult::Adapted {
                    corrected_data,
                    mapping,
                });
            }
        }

        // Step 3: Check SQLite (<2ms)
        match self.graph.lookup(&failed_field, tenant_id) {
            Ok(Some(mapping)) => {
                if mapping.approved {
                    // Warm up the cache for next time
                    if let Err(e) = self.cache.insert(&failed_field, &mapping, tenant_id) {
                        tracing::warn!("DagAdapter: cache warm-up failed: {}", e);
                    }

                    let corrected_data = self.inject_mapping(original_data, &mapping);
                    tracing::debug!(
                        node_id = %failed_node_id,
                        field = %failed_field,
                        destination = %mapping.destination,
                        "DagAdapter: SQLite hit, injecting corrected parameter"
                    );
                    return Ok(AdaptResult::Adapted {
                        corrected_data,
                        mapping,
                    });
                }
                // Mapping exists but not yet approved — don't use it
                tracing::debug!(
                    field = %failed_field,
                    "DagAdapter: mapping found but not approved, triggering learning flow"
                );
            }
            Ok(None) => {
                tracing::debug!(
                    field = %failed_field,
                    "DagAdapter: no mapping found, triggering learning flow"
                );
            }
            Err(e) => {
                tracing::warn!("DagAdapter: SQLite lookup error: {}", e);
            }
        }

        // Step 5: No mapping found → trigger learning flow
        Ok(AdaptResult::NoMapping {
            failed_field,
        })
    }

    /// Extracts the likely failed field name from an error message.
    ///
    /// Uses simple string parsing (no regex dependency).
    /// Looks for quoted identifiers or words after keywords.
    fn extract_failed_field(&self, error_message: &str) -> String {
        // Strategy 1: Extract text between single/double quotes
        let lower = error_message.to_lowercase();
        for (i, c) in lower.char_indices() {
            if c == '\'' || c == '"' || c == '`' {
                // Find closing quote
                let rest = &error_message[i + 1..];
                if let Some(end) = rest.find(|c2: char| c2 == '\'' || c2 == '"' || c2 == '`') {
                    let content = &rest[..end];
                    if content.len() > 2
                        && content
                            .chars()
                            .all(|c2| c2.is_alphanumeric() || c2 == '_')
                        && content.chars().next().map_or(false, |c2| c2.is_lowercase())
                    {
                        return content.to_string();
                    }
                }
            }
        }

        // Strategy 2: Look for keywords followed by field names
        let keywords = ["field", "key", "parameter", "column", "property"];
        for kw in &keywords {
            if let Some(pos) = lower.find(kw) {
                let after = &lower[pos + kw.len()..];
                let trimmed = after.trim_start_matches(|c: char| c == ' ' || c == ':' || c == '=');
                if let Some(word) = trimmed.split_whitespace().next() {
                    let cleaned = word.trim_matches(|c: char| !c.is_alphanumeric() && c != '_');
                    if cleaned.len() > 2 {
                        return cleaned.to_string();
                    }
                }
            }
        }

        // Strategy 3: Fallback — first identifier-like word
        error_message
            .split(|c: char| !c.is_alphanumeric() && c != '_')
            .find(|s| {
                !s.is_empty()
                    && s.len() > 2
                    && s.chars().next().map_or(false, |c| c.is_lowercase())
            })
            .unwrap_or("unknown_field")
            .to_string()
    }

    /// Inyecta el mapeo aprendido en el payload del nodo.
    ///
    /// Reemplaza la clave original por la mapeada, preserving all other data.
    fn inject_mapping(
        &self,
        original: &HashMap<String, NodeValue>,
        mapping: &SemanticMapping,
    ) -> HashMap<String, NodeValue> {
        let mut adapted = original.clone();
        // Replace the original key with the mapped destination
        if let Some(value) = adapted.remove(&mapping.origin) {
            adapted.insert(mapping.destination.clone(), value);
        }
        // Also keep the original as a reference (optional, for debugging)
        adapted.insert(
            format!("_adapted_from_{}", mapping.origin),
            NodeValue::Text(mapping.origin.clone()),
        );
        adapted
    }

    /// Batch-adapt multiple failed fields at once.
    ///
    /// Useful when a single node failure involves multiple missing fields.
    pub fn try_adapt_batch(
        &self,
        failed_node_id: &NodeId,
        failed_fields: &[String],
        original_data: &HashMap<String, NodeValue>,
        tenant_id: &str,
    ) -> Result<HashMap<String, AdaptResult>, DagAdapterError> {
        let mut results = HashMap::new();
        for field in failed_fields {
            let result = self.try_adapt(failed_node_id, &format!("field '{}' not found", field), original_data, tenant_id)?;
            results.insert(field.clone(), result);
        }
        Ok(results)
    }
}


