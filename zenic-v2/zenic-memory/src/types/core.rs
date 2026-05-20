//! Core type definitions for the Adaptive Binary Memory Chip.
//!
//! Fundamental value types: semantic mappings, learning mechanisms,
//! and typed DAG node values.
//!
//! Key invariants:
//! - The LLM NEVER generates content — only emits boolean verdict [T1+T2]
//! - Memory does NOT alter LLM weights — modifies DAG config + Policy Engine [T2]
//! - rkyv for transit (zero-copy), bincode for persistence, serde_json for APIs only [T3]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// LearningMechanism — The 3 Learning Mechanisms [T1]
// ---------------------------------------------------------------------------

/// The mechanism by which a semantic mapping was learned.
///
/// Each mechanism corresponds to a specific learning pattern:
/// - **SchemaDrift** — DB column renames: "estatus_cliente → estado_id" [T1-4,T1-7]
/// - **IntentRouting** — MCP tool matching: "tumba la cuenta → cancelar_suscripcion" [T1-5,T1-8]
/// - **PolicyRefinement** — Gray-area classification: "reparación urgente → gasto_crítico" [T1-6,T1-9]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LearningMechanism {
    /// Mechanism 1: Schema Drift — DB column renames and field adaptations.
    SchemaDrift,
    /// Mechanism 2: Intent Routing — Ambiguous user intent → MCP tool matching.
    IntentRouting,
    /// Mechanism 3: Policy Refinement — Gray-area security/business policy classification.
    PolicyRefinement,
    /// Built-in ontology mapping (not learned, pre-defined).
    OntologyBase,
}

impl LearningMechanism {
    /// Returns the string representation used in SQLite storage.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::SchemaDrift => "schema_drift",
            Self::IntentRouting => "intent_routing",
            Self::PolicyRefinement => "policy_refinement",
            Self::OntologyBase => "ontology_base",
        }
    }

    /// Parses a mechanism from its string representation.
    pub fn from_str_lossy(s: &str) -> Self {
        match s {
            "schema_drift" => Self::SchemaDrift,
            "intent_routing" => Self::IntentRouting,
            "policy_refinement" => Self::PolicyRefinement,
            "ontology_base" => Self::OntologyBase,
            _ => Self::OntologyBase,
        }
    }

    /// Returns all learning mechanisms (excluding OntologyBase).
    pub fn learnable() -> &'static [LearningMechanism] {
        &[Self::SchemaDrift, Self::IntentRouting, Self::PolicyRefinement]
    }
}

impl std::fmt::Display for LearningMechanism {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ---------------------------------------------------------------------------
// SemanticMapping — Deterministic Knowledge Graph Record [T1-2, T1-3]
// ---------------------------------------------------------------------------

/// A single semantic mapping in the knowledge graph.
///
/// Represents a directed relationship: `origin --[relation]--> destination`.
/// Each mapping is isolated per tenant and tracks confidence, approval status,
/// and optional Merkle hash for integrity verification.
///
/// Example: "cobro" → "synonym_of" → "factura"
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SemanticMapping {
    /// Unique identifier (UUID v4 string).
    pub mapping_id: String,
    /// The source term / concept (e.g., "cobro").
    pub origin: String,
    /// The relationship type (e.g., "synonym_of", "action_for", "maps_to").
    pub relation: String,
    /// The target term / concept (e.g., "factura").
    pub destination: String,
    /// How this mapping was learned.
    pub mechanism: LearningMechanism,
    /// Confidence score (0–100). Set after HITL approval.
    pub confidence: u8,
    /// Tenant isolation key. `"__anonymous__"` for unauthenticated,
    /// `"__ontology_base__"` for built-in ontology mappings.
    pub tenant_id: String,
    /// Unix epoch milliseconds when this mapping was created.
    pub created_at: i64,
    /// Whether this mapping has been approved by HITL.
    pub approved: bool,
    /// BLAKE3 Merkle hash seal after approval.
    pub merkle_hash: Option<String>,
}

impl SemanticMapping {
    /// Creates a new unapproved semantic mapping.
    pub fn new(
        mapping_id: String,
        origin: String,
        relation: String,
        destination: String,
        mechanism: LearningMechanism,
    ) -> Self {
        Self {
            mapping_id,
            origin,
            relation,
            destination,
            mechanism,
            confidence: 0,
            tenant_id: "__anonymous__".to_string(),
            created_at: now_millis(),
            approved: false,
            merkle_hash: None,
        }
    }

    /// Creates an ontology-base mapping with standard defaults.
    pub fn ontology_base(
        mapping_id: String,
        origin: String,
        relation: String,
        destination: String,
    ) -> Self {
        Self {
            mapping_id,
            origin,
            relation,
            destination,
            mechanism: LearningMechanism::OntologyBase,
            confidence: 80,
            tenant_id: "__ontology_base__".to_string(),
            created_at: 0,
            approved: true,
            merkle_hash: None,
        }
    }

    /// Generates the binary question for IA classification.
    /// The LLM only answers YES/NO — never generates content.
    pub fn binary_question(&self) -> String {
        format!(
            "¿Es correcto mapear '{}' como {} de '{}'?",
            self.origin, self.relation, self.destination
        )
    }

    /// Creates a cache key for this mapping.
    pub fn cache_key(&self) -> String {
        format!("{}::{}", self.tenant_id, self.origin)
    }
}

/// Returns current Unix epoch in milliseconds.
pub(crate) fn now_millis() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}

// ---------------------------------------------------------------------------
// NodeValue — Replaces serde_json::Value in Hot Paths [T3]
// ---------------------------------------------------------------------------

/// Typed value for DAG node data. Replaces `serde_json::Value` in hot paths
/// for zero-copy access via rkyv in the SharedMemoryBus and DAG context.
///
/// serde_json::Value is still used for external APIs only.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum NodeValue {
    /// Null / absent value.
    Null,
    /// Boolean flag.
    Bool(bool),
    /// Signed 64-bit integer.
    I64(i64),
    /// Unsigned 64-bit integer.
    U64(u64),
    /// 64-bit floating point.
    F64(f64),
    /// UTF-8 text string.
    Text(String),
    /// Binary blob (serialized sub-graph or config).
    Binary(Vec<u8>),
    /// Ordered array of values.
    Array(Vec<NodeValue>),
    /// Key-value map (preserves insertion order via Vec).
    Map(Vec<(String, NodeValue)>),
}

impl NodeValue {
    // ── Accessor methods ──

    /// Returns `true` if this is a [`Null`](NodeValue::Null) value.
    pub fn is_null(&self) -> bool {
        matches!(self, Self::Null)
    }

    /// Returns the inner bool if this is a [`Bool`](NodeValue::Bool).
    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Self::Bool(b) => Some(*b),
            _ => None,
        }
    }

    /// Returns the inner i64 if this is an [`I64`](NodeValue::I64).
    pub fn as_i64(&self) -> Option<i64> {
        match self {
            Self::I64(v) => Some(*v),
            Self::U64(v) => i64::try_from(*v).ok(),
            _ => None,
        }
    }

    /// Returns the inner f64 if this is an [`F64`](NodeValue::F64).
    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Self::F64(v) => Some(*v),
            Self::I64(v) => Some(*v as f64),
            _ => None,
        }
    }

    /// Returns the inner str if this is a [`Text`](NodeValue::Text).
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Self::Text(s) => Some(s),
            _ => None,
        }
    }

    // ── JSON conversion ──

    /// Converts a `serde_json::Value` to a `NodeValue`.
    ///
    /// Used at API boundaries where external systems send JSON.
    /// Binary data is represented as base64-encoded strings.
    pub fn from_json_value(val: serde_json::Value) -> Self {
        match val {
            serde_json::Value::Null => Self::Null,
            serde_json::Value::Bool(b) => Self::Bool(b),
            serde_json::Value::Number(n) => {
                if let Some(i) = n.as_i64() {
                    Self::I64(i)
                } else if let Some(u) = n.as_u64() {
                    Self::U64(u)
                } else if let Some(f) = n.as_f64() {
                    Self::F64(f)
                } else {
                    Self::Null
                }
            }
            serde_json::Value::String(s) => Self::Text(s),
            serde_json::Value::Array(arr) => {
                Self::Array(arr.into_iter().map(Self::from_json_value).collect())
            }
            serde_json::Value::Object(obj) => {
                Self::Map(
                    obj.into_iter()
                        .map(|(k, v)| (k, Self::from_json_value(v)))
                        .collect(),
                )
            }
        }
    }

    /// Converts this `NodeValue` back to a `serde_json::Value`.
    ///
    /// Used at API boundaries for external output.
    /// Binary data is encoded as base64 string.
    pub fn to_json_value(&self) -> serde_json::Value {
        match self {
            Self::Null => serde_json::Value::Null,
            Self::Bool(b) => serde_json::json!(b),
            Self::I64(v) => serde_json::json!(v),
            Self::U64(v) => serde_json::json!(v),
            Self::F64(v) => serde_json::json!(v),
            Self::Text(s) => serde_json::json!(s),
            Self::Binary(data) => {
                use base64::Engine;
                let encoded = base64::engine::general_purpose::STANDARD.encode(data);
                serde_json::json!(encoded)
            }
            Self::Array(arr) => {
                serde_json::Value::Array(arr.iter().map(Self::to_json_value).collect())
            }
            Self::Map(pairs) => {
                let map: serde_json::Map<String, serde_json::Value> = pairs
                    .iter()
                    .map(|(k, v)| (k.clone(), Self::to_json_value(v)))
                    .collect();
                serde_json::Value::Object(map)
            }
        }
    }

    /// Convenience: convert a `HashMap<String, serde_json::Value>` to `HashMap<String, NodeValue>`.
    pub fn convert_map(
        input: &HashMap<String, serde_json::Value>,
    ) -> HashMap<String, NodeValue> {
        input
            .iter()
            .map(|(k, v)| (k.clone(), Self::from_json_value(v.clone())))
            .collect()
    }

    /// Convenience: convert a `HashMap<String, NodeValue>` to `HashMap<String, serde_json::Value>`.
    pub fn unconvert_map(
        input: &HashMap<String, NodeValue>,
    ) -> HashMap<String, serde_json::Value> {
        input.iter().map(|(k, v)| (k.clone(), v.to_json_value())).collect()
    }
}

impl Default for NodeValue {
    fn default() -> Self {
        Self::Null
    }
}
