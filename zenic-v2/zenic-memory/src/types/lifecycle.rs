//! Lifecycle type definitions for the Adaptive Binary Memory Chip.
//!
//! Types related to the learning verdict pipeline, HITL approval,
//! hypothesis management, and subscription-based feature gating.

use serde::{Deserialize, Serialize};

use super::core::{LearningMechanism, SemanticMapping, now_millis};
use crate::errors::MemoryError;

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
