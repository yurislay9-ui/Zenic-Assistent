//! Memory-related types: NodeValue, MemoryApprovalRequest, FeatureGate, SubscriptionTier.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::errors::MemoryError;
use super::learning::{LearningMechanism, LearningVerdict, now_millis};

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
// SubscriptionTier — Re-exported from zenic-subscription [T1]
// ---------------------------------------------------------------------------

/// Subscription tier for feature gating in the memory layer.
///
/// Re-exported from `zenic_subscription::types::SubscriptionTierName` to
/// ensure a single source of truth for tier definitions across crates.
///
/// Maps directly to the pricing tiers in zenic-subscription:
/// - Starter: $29/mo — Schema Drift only, 10 mappings/mes, LRU 100
/// - Business: $99/mo — +Intent Routing, 50 mappings/mes, LRU 500
/// - Enterprise: $299/mo — All 3 + Ontología, unlimited, LRU 2000
/// - OnPremiseEnterprise: $799/mo — All + Export/Import + Custom, unlimited
pub use zenic_subscription::types::SubscriptionTierName as SubscriptionTier;

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
    ///
    /// Memory-specific tier limits (mappings, cache, mechanisms, etc.) are
    /// defined here since they belong to the memory layer, not the
    /// subscription crate's `SubscriptionTierName`.
    pub fn for_tier(tier: SubscriptionTier) -> Self {
        let (max_mappings, lru_size, mechanisms, ontology, export, custom) = match tier {
            SubscriptionTier::Starter => (
                10,
                100,
                vec![LearningMechanism::SchemaDrift],
                false,
                false,
                false,
            ),
            SubscriptionTier::Business => (
                50,
                500,
                vec![LearningMechanism::SchemaDrift, LearningMechanism::IntentRouting],
                false,
                false,
                false,
            ),
            SubscriptionTier::Enterprise => (
                u32::MAX,
                2000,
                LearningMechanism::learnable().to_vec(),
                true,
                false,
                false,
            ),
            SubscriptionTier::OnPremiseEnterprise => (
                u32::MAX,
                usize::MAX,
                LearningMechanism::learnable().to_vec(),
                true,
                true,
                true,
            ),
        };
        Self {
            max_mappings_per_month: max_mappings,
            lru_cache_size: lru_size,
            mechanisms_allowed: mechanisms,
            ontology_access: ontology,
            export_import: export,
            custom_ontology: custom,
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
