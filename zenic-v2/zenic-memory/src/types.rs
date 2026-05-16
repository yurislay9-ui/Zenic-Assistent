//! Core type definitions for the Adaptive Binary Memory Chip.
//!
//! These types represent the fundamental data structures that flow through
//! the memory pipeline: semantic mappings, learning verdicts, approval
//! requests, node values, subscription tiers, and feature gates.
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
fn now_millis() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}

// ---------------------------------------------------------------------------
// LearningVerdict — 4-Layer Verdict Result [T2]
// ---------------------------------------------------------------------------

/// Result from the 4-layer verdict pipeline.
///
/// Wraps the mapping with IA classification results and evidence.
/// The LLM NEVER generates content — only emits boolean verdict.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LearningVerdict {
    /// The mapping being evaluated.
    pub mapping: SemanticMapping,
    /// The exact binary question asked to the IA.
    pub ia_question: String,
    /// IA response: true = YES (accept mapping), false = NO (reject).
    pub ia_response: bool,
    /// Evidence in favor (from Layer 2: EvidenceCollector).
    pub evidence_for: Vec<String>,
    /// Evidence against (from Layer 2: EvidenceCollector).
    pub evidence_against: Vec<String>,
    /// Consensus score from Layer 3 (ConsensusResolver).
    pub consensus_score: f64,
    /// Which layer resolved the verdict (1-4).
    pub layer_resolved: u8,
}

impl LearningVerdict {
    /// Creates a Layer 1 (deterministic) bypass verdict — no IA needed.
    pub fn deterministic_accept(mapping: SemanticMapping) -> Self {
        let question = mapping.binary_question();
        Self {
            mapping,
            ia_question: question,
            ia_response: true,
            evidence_for: vec!["deterministic_match".to_string()],
            evidence_against: vec![],
            consensus_score: 1.0,
            layer_resolved: 1,
        }
    }

    /// Creates a Layer 4 (IA) verdict.
    pub fn ia_verdict(
        mapping: SemanticMapping,
        ia_response: bool,
        evidence_for: Vec<String>,
        evidence_against: Vec<String>,
        consensus_score: f64,
    ) -> Self {
        let question = mapping.binary_question();
        Self {
            mapping,
            ia_question: question,
            ia_response,
            evidence_for,
            evidence_against,
            consensus_score,
            layer_resolved: 4,
        }
    }

    /// Returns true if resolved at Layer 1 (deterministic, no IA).
    pub fn is_deterministic(&self) -> bool {
        self.layer_resolved == 1
    }
}

// ---------------------------------------------------------------------------
// MemoryApprovalRequest — GRIETA 3: HITL Mandatory Fields [T2-13]
// ---------------------------------------------------------------------------

/// HITL approval payload with MANDATORY fields.
///
/// The YAML compilation FAILS if this does not validate.
/// No "ok" justification allowed — requires structured, meaningful input.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MemoryApprovalRequest {
    // ── MANDATORY fields — must pass validate() ──

    /// Admin must confirm reviewing evidence from Layers 2 and 3.
    /// MUST be `true` for approval to proceed.
    pub admin_evidence_review: bool,

    /// Admin justification explaining WHY this mapping is valid for business.
    /// MUST be at least 50 characters — no "ok" allowed.
    pub admin_justification: String,

    /// Admin must explicitly assume responsibility for injecting
    /// this new rule into production.
    /// MUST be `true` for approval to proceed.
    pub risk_acknowledgment: bool,

    /// Crypto-linked session ID of the admin making the approval.
    /// MUST be non-empty.
    pub admin_session_id: String,

    // ── Auto-populated fields (no admin input required) ──

    /// The semantic mapping being approved.
    pub mapping_id: String,

    /// The exact binary question asked to the IA.
    pub ia_question: String,

    /// IA response (YES/NO).
    pub ia_response: bool,

    /// Evidence in favor (Layer 2).
    pub evidence_for: Vec<String>,

    /// Evidence against (Layer 2).
    pub evidence_against: Vec<String>,

    /// Consensus score (Layer 3).
    pub consensus_score: f64,
}

impl MemoryApprovalRequest {
    /// Minimum character count for admin justification.
    pub const MIN_JUSTIFICATION_LEN: usize = 50;

    /// Validates that all mandatory fields comply with the structure.
    ///
    /// Returns `Err(MemoryError)` if any mandatory field is missing or invalid.
    /// The YAML renderer also verifies this before compiling.
    pub fn validate(&self) -> Result<(), MemoryError> {
        if !self.admin_evidence_review {
            return Err(MemoryError::EvidenceReviewRequired);
        }
        let trimmed = self.admin_justification.trim();
        if trimmed.len() < Self::MIN_JUSTIFICATION_LEN {
            return Err(MemoryError::JustificationTooShort {
                provided: trimmed.len(),
                required: Self::MIN_JUSTIFICATION_LEN,
            });
        }
        if !self.risk_acknowledgment {
            return Err(MemoryError::RiskAcknowledgmentRequired);
        }
        if self.admin_session_id.trim().is_empty() {
            return Err(MemoryError::SessionIdRequired);
        }
        Ok(())
    }

    /// Creates a new approval request from a learning verdict.
    pub fn from_verdict(verdict: &LearningVerdict, admin_session_id: String) -> Self {
        Self {
            admin_evidence_review: false,
            admin_justification: String::new(),
            risk_acknowledgment: false,
            admin_session_id,
            mapping_id: verdict.mapping.mapping_id.clone(),
            ia_question: verdict.ia_question.clone(),
            ia_response: verdict.ia_response,
            evidence_for: verdict.evidence_for.clone(),
            evidence_against: verdict.evidence_against.clone(),
            consensus_score: verdict.consensus_score,
        }
    }
}

// ---------------------------------------------------------------------------
// Hypothesis — Pre-IA Proposal [T1]
// ---------------------------------------------------------------------------

/// A hypothesis generated by the deterministic layer for IA classification.
///
/// "La Capa Estructurada Propone, la IA Clasifica SÍ/NO, el Humano Valida."
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Hypothesis {
    /// The origin term that triggered the hypothesis.
    pub origin: String,
    /// Proposed relation type.
    pub proposed_relation: String,
    /// Proposed destination term.
    pub proposed_destination: String,
    /// Which mechanism generated this hypothesis.
    pub mechanism: LearningMechanism,
    /// Why this hypothesis was generated (context).
    pub context: String,
    /// Deterministic confidence before IA classification.
    pub confidence_before_ia: f64,
    /// The binary YES/NO question for the IA.
    pub binary_question: String,
}

impl Hypothesis {
    /// Creates a new hypothesis.
    pub fn new(
        origin: impl Into<String>,
        proposed_relation: impl Into<String>,
        proposed_destination: impl Into<String>,
        mechanism: LearningMechanism,
        context: impl Into<String>,
        confidence_before_ia: f64,
    ) -> Self {
        let origin = origin.into();
        let proposed_relation = proposed_relation.into();
        let proposed_destination = proposed_destination.into();
        let binary_question = format!(
            "¿Es correcto mapear '{}' como {} de '{}'?",
            origin, proposed_relation, proposed_destination
        );
        Self {
            origin,
            proposed_relation,
            proposed_destination,
            mechanism,
            context: context.into(),
            confidence_before_ia,
            binary_question,
        }
    }

    /// Converts this hypothesis into a SemanticMapping (pending approval).
    pub fn to_mapping(&self, tenant_id: &str) -> SemanticMapping {
        SemanticMapping {
            mapping_id: uuid::Uuid::new_v4().to_string(),
            origin: self.origin.clone(),
            relation: self.proposed_relation.clone(),
            destination: self.proposed_destination.clone(),
            mechanism: self.mechanism,
            confidence: (self.confidence_before_ia * 100.0) as u8,
            tenant_id: tenant_id.to_string(),
            created_at: now_millis(),
            approved: false,
            merkle_hash: None,
        }
    }
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

// ---------------------------------------------------------------------------
// SubscriptionTier — Feature Gating by Tier [T1]
// ---------------------------------------------------------------------------

/// Subscription tier for feature gating in the memory layer.
///
/// Maps directly to the pricing tiers in zenic-subscription:
/// - Starter: $29/mo — Schema Drift only, 10 mappings/mes, LRU 100
/// - Business: $99/mo — +Intent Routing, 50 mappings/mes, LRU 500
/// - Enterprise: $299/mo — All 3 + Ontología, unlimited, LRU 2000
/// - On-Premise: $799/mo — All + Export/Import + Custom, unlimited
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SubscriptionTier {
    Starter,
    Business,
    Enterprise,
    OnPremise,
}

impl SubscriptionTier {
    /// Returns the tier rank for comparison (0 = lowest).
    pub fn rank(&self) -> u8 {
        match self {
            Self::Starter => 0,
            Self::Business => 1,
            Self::Enterprise => 2,
            Self::OnPremise => 3,
        }
    }

    /// Maximum semantic mappings per month for this tier.
    pub fn max_mappings_per_month(&self) -> u32 {
        match self {
            Self::Starter => 10,
            Self::Business => 50,
            Self::Enterprise => u32::MAX,
            Self::OnPremise => u32::MAX,
        }
    }

    /// Maximum LRU cache size for this tier.
    pub fn lru_cache_size(&self) -> usize {
        match self {
            Self::Starter => 100,
            Self::Business => 500,
            Self::Enterprise => 2000,
            Self::OnPremise => usize::MAX,
        }
    }

    /// Learning mechanisms allowed for this tier.
    pub fn mechanisms_allowed(&self) -> Vec<LearningMechanism> {
        match self {
            Self::Starter => vec![LearningMechanism::SchemaDrift],
            Self::Business => vec![LearningMechanism::SchemaDrift, LearningMechanism::IntentRouting],
            Self::Enterprise | Self::OnPremise => LearningMechanism::learnable().to_vec(),
        }
    }

    /// Whether this tier has ontology access.
    pub fn ontology_access(&self) -> bool {
        matches!(self, Self::Enterprise | Self::OnPremise)
    }

    /// Whether this tier has export/import capability.
    pub fn export_import(&self) -> bool {
        matches!(self, Self::OnPremise)
    }
}

impl std::fmt::Display for SubscriptionTier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Starter => write!(f, "Starter"),
            Self::Business => write!(f, "Business"),
            Self::Enterprise => write!(f, "Enterprise"),
            Self::OnPremise => write!(f, "OnPremise"),
        }
    }
}

// ---------------------------------------------------------------------------
// FeatureGate — Subscription-based Access Control [T1]
// ---------------------------------------------------------------------------

/// Feature gate configuration for a subscription tier.
///
/// Enforces per-tier quotas on mappings, cache, mechanisms, and ontology.
#[derive(Debug, Clone, PartialEq)]
pub struct FeatureGate {
    /// The subscription tier this gate applies to.
    pub tier: SubscriptionTier,
    /// Maximum semantic mappings per month.
    pub max_mappings_per_month: u32,
    /// Maximum LRU cache entries.
    pub lru_cache_size: usize,
    /// Learning mechanisms allowed.
    pub mechanisms_allowed: Vec<LearningMechanism>,
    /// Whether ontology access is granted.
    pub ontology_access: bool,
    /// Whether export/import is allowed.
    pub export_import: bool,
    /// Whether custom ontology is allowed.
    pub custom_ontology: bool,
}

impl FeatureGate {
    /// Creates a FeatureGate for the given subscription tier.
    pub fn for_tier(tier: SubscriptionTier) -> Self {
        Self {
            max_mappings_per_month: tier.max_mappings_per_month(),
            lru_cache_size: tier.lru_cache_size(),
            mechanisms_allowed: tier.mechanisms_allowed(),
            ontology_access: tier.ontology_access(),
            export_import: tier.export_import(),
            custom_ontology: tier == SubscriptionTier::OnPremise,
            tier,
        }
    }

    /// Checks if a specific learning mechanism is allowed for this tier.
    pub fn is_mechanism_allowed(&self, mechanism: LearningMechanism) -> bool {
        self.mechanisms_allowed.contains(&mechanism)
    }

    /// Checks if the mapping quota has been exceeded.
    pub fn is_mapping_quota_exceeded(&self, current_count: u32) -> bool {
        current_count >= self.max_mappings_per_month
    }
}

// ---------------------------------------------------------------------------
// Import MemoryError for MemoryApprovalRequest::validate
// ---------------------------------------------------------------------------

use crate::errors::MemoryError;
