//! Domain Safety Gate — Types.
//!
//! Shared types for the 4-layer safety validation pipeline.

use serde::{Deserialize, Serialize};
use std::fmt;

use crate::categories::NicheCategory;
use crate::compliance::ComplianceResult;
use crate::sensitivity::DataSensitivity;
use crate::verdict::SafetyVerdict;

// ---------------------------------------------------------------------------
// DomainSafetyCheckResult
// ---------------------------------------------------------------------------

/// Result of the full 4-layer domain safety check.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainSafetyCheckResult {
    /// Verdict from Layer 1 (base gate).
    pub base_verdict: SafetyVerdict,
    /// Verdict from Layer 2 (domain rules).
    pub domain_verdict: SafetyVerdict,
    /// Final verdict after all 4 layers.
    pub final_verdict: SafetyVerdict,
    /// The niche category context.
    pub niche_category: NicheCategory,
    /// The data sensitivity level.
    pub data_sensitivity: DataSensitivity,
    /// Names of domain rules that matched.
    pub domain_rules_matched: Vec<String>,
    /// Compliance check results.
    pub compliance_results: Vec<ComplianceResult>,
    /// Whether sensitivity escalation was applied.
    pub escalation_applied: bool,
    /// Human-readable reason for the final verdict.
    pub reason: String,
    /// Whether the action can proceed (not DENY or RATE_LIMITED).
    pub can_proceed: bool,
}

impl fmt::Display for DomainSafetyCheckResult {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "DomainSafetyCheckResult(final={}, category={}, escalation={}, proceed={})",
            self.final_verdict,
            self.niche_category,
            self.escalation_applied,
            self.can_proceed
        )
    }
}
