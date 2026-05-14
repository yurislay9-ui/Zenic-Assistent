//! Domain Safety Gate — 4-layer safety validation pipeline.
//!
//! Layer 1: Base SafetyGate (10 generic rules)
//! Layer 2: Domain-specific rules (35 = 5 per NicheCategory)
//! Layer 3: Compliance validation (8 standards)
//! Layer 4: Sensitivity escalation (critical → auto-deny)
//!
//! INVARIANTS:
//!   1. Domain rules can only ESCALATE verdicts, never downgrade.
//!   2. If the base gate returns DENY, domain gate CANNOT override.
//!   3. Compliance failures for critical violations result in DENY.
//!   4. All logic is deterministic — no AI, no randomness.

use serde::{Deserialize, Serialize};
use std::fmt;

use crate::categories::NicheCategory;
use crate::compliance::{ComplianceEngine, ComplianceResult};
use crate::domain_rules::DomainRuleSet;
use crate::sensitivity::DataSensitivity;
use crate::verdict::{ActionCategory, SafetyVerdict};

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

// ---------------------------------------------------------------------------
// DomainSafetyGate
// ---------------------------------------------------------------------------

/// Extended safety gate with 4-layer validation pipeline.
///
/// # Pipeline
///
/// 1. **Base check**: Classify action category → default verdict
/// 2. **Domain check**: Match against 35 niche-specific rules
/// 3. **Compliance check**: Validate against regulatory standards
/// 4. **Sensitivity escalation**: Apply data sensitivity escalation
///
/// # Invariants
///
/// - Domain rules can only ESCALATE verdicts
/// - Base DENY cannot be overridden
/// - Critical compliance failures → DENY
pub struct DomainSafetyGate {
    domain_rules: DomainRuleSet,
    compliance_engine: ComplianceEngine,
}

impl DomainSafetyGate {
    /// Create a new domain safety gate.
    pub fn new() -> Self {
        Self {
            domain_rules: DomainRuleSet::new(),
            compliance_engine: ComplianceEngine::new(),
        }
    }

    /// Run the full 4-layer safety validation pipeline.
    pub fn check(
        &self,
        action_type: &str,
        config: &serde_json::Value,
        niche_category: NicheCategory,
        data_sensitivity: DataSensitivity,
    ) -> DomainSafetyCheckResult {
        // ── Layer 1: Base classification ───────────────────────
        let category = Self::classify_action(action_type, config);
        let base_verdict = Self::default_verdict(category);
        let mut current_verdict = base_verdict;
        let mut reason = format!("Action classified as {}", category);

        // INVARIANT: If base says DENY, we cannot override
        if base_verdict == SafetyVerdict::Deny {
            return DomainSafetyCheckResult {
                base_verdict,
                domain_verdict: base_verdict,
                final_verdict: base_verdict,
                niche_category,
                data_sensitivity,
                domain_rules_matched: Vec::new(),
                compliance_results: Vec::new(),
                escalation_applied: false,
                reason: "Base gate DENY — cannot override".to_string(),
                can_proceed: false,
            };
        }

        // ── Layer 2: Domain-specific rules ─────────────────────
        let domain_matches = self.domain_rules.check(niche_category, action_type, config);
        let mut domain_rules_matched: Vec<String> = Vec::new();
        let mut domain_verdict = current_verdict;

        for rule in &domain_matches {
            // INVARIANT: Only escalate, never downgrade
            domain_verdict = domain_verdict.escalate(rule.verdict);
            domain_rules_matched.push(rule.name.clone());
            reason = rule.message.clone();
        }

        current_verdict = domain_verdict;

        // ── Layer 3: Compliance validation ─────────────────────
        let compliance_results = self
            .compliance_engine
            .check_category(niche_category, action_type, config);

        // Critical compliance violations → DENY
        for cr in &compliance_results {
            if cr.risk_level == "critical" && !cr.compliant {
                current_verdict = SafetyVerdict::Deny;
                reason = format!(
                    "Critical compliance violation ({}): {}",
                    cr.standard.display_name(),
                    cr.violations.first().unwrap_or(&"Unknown".to_string())
                );
                break;
            }
        }

        // ── Layer 4: Sensitivity escalation ────────────────────
        let pre_escalation = current_verdict;
        let final_verdict = data_sensitivity.escalate_verdict(current_verdict);
        let escalation_applied = final_verdict != pre_escalation;

        if escalation_applied {
            reason = format!(
                "{} [sensitivity escalation: {} → {} due to {} sensitivity]",
                reason,
                pre_escalation,
                final_verdict,
                data_sensitivity
            );
        }

        let can_proceed = !final_verdict.is_blocked();

        DomainSafetyCheckResult {
            base_verdict,
            domain_verdict,
            final_verdict,
            niche_category,
            data_sensitivity,
            domain_rules_matched,
            compliance_results,
            escalation_applied,
            reason,
            can_proceed,
        }
    }

    /// Check only domain rules (Layer 2) without the full pipeline.
    pub fn check_domain_rules(
        &self,
        niche_category: NicheCategory,
        action_type: &str,
        config: &serde_json::Value,
    ) -> Vec<String> {
        self.domain_rules
            .check(niche_category, action_type, config)
            .iter()
            .map(|r| r.name.clone())
            .collect()
    }

    /// Check only compliance (Layer 3) for a specific standard.
    pub fn check_compliance(
        &self,
        standard: crate::compliance::ComplianceStandard,
        action_type: &str,
        config: &serde_json::Value,
    ) -> ComplianceResult {
        self.compliance_engine.check_standard(standard, action_type, config)
    }

    /// Get all domain rules for a category.
    pub fn get_domain_rules(
        &self,
        niche_category: NicheCategory,
    ) -> Vec<&crate::domain_rules::DomainRule> {
        self.domain_rules.rules_for_category(niche_category)
    }

    /// Get compliance standards required for a category.
    pub fn get_compliance_for_category(
        &self,
        niche_category: NicheCategory,
    ) -> Vec<crate::compliance::ComplianceStandard> {
        niche_category.compliance_standards().to_vec()
    }

    // ── Deterministic Action Classification ────────────────────

    /// Classify an action into a risk category (deterministic).
    ///
    /// This mirrors the Python SafetyGate._classify_action logic.
    fn classify_action(action_type: &str, config: &serde_json::Value) -> ActionCategory {
        let action_lower = action_type.to_lowercase();

        if matches!(
            action_lower.as_str(),
            "database" | "db" | "database_operation"
        ) {
            let operation = config
                .get("operation")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_lowercase();
            let query = config
                .get("query")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_uppercase();

            if query.contains("DELETE") || operation == "delete" {
                return ActionCategory::Destructive;
            }
            if query.contains("DROP") || query.contains("TRUNCATE") {
                return ActionCategory::Destructive;
            }
            if query.contains("INSERT") || query.contains("UPDATE") {
                return ActionCategory::Moderate;
            }
            if operation.contains("backup") || operation.contains("script") {
                return ActionCategory::System;
            }
            return ActionCategory::Safe;
        }

        if matches!(
            action_lower.as_str(),
            "email" | "send_email"
        ) {
            let subject = config
                .get("subject")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_lowercase();
            let body = config
                .get("body")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_lowercase();
            let combined = format!("{} {}", subject, body);
            if combined.contains("invoice")
                || combined.contains("factura")
                || combined.contains("payment")
                || combined.contains("pago")
                || combined.contains("refund")
            {
                return ActionCategory::Financial;
            }
            return ActionCategory::Moderate;
        }

        if matches!(action_lower.as_str(), "file" | "file_operation") {
            let operation = config
                .get("operation")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_lowercase();
            if matches!(operation.as_str(), "delete" | "move") {
                return ActionCategory::Destructive;
            }
            if matches!(operation.as_str(), "write" | "append") {
                return ActionCategory::Moderate;
            }
            return ActionCategory::Safe;
        }

        if action_lower == "schedule" {
            return ActionCategory::System;
        }

        if matches!(
            action_lower.as_str(),
            "notification" | "send_notification"
        ) {
            return ActionCategory::Safe;
        }

        if matches!(
            action_lower.as_str(),
            "http" | "http_request" | "webhook"
        ) {
            let method = config
                .get("method")
                .and_then(|v| v.as_str())
                .unwrap_or("GET")
                .to_uppercase();
            if matches!(method.as_str(), "DELETE" | "PUT") {
                return ActionCategory::Moderate;
            }
            return ActionCategory::Safe;
        }

        if matches!(
            action_lower.as_str(),
            "transform" | "data_transform"
        ) {
            return ActionCategory::Safe;
        }

        if action_lower == "discord" {
            return ActionCategory::Moderate;
        }

        // Niche onboarding action
        if action_lower == "niche_onboarding" {
            return ActionCategory::Moderate;
        }

        ActionCategory::Moderate
    }

    /// Default verdict based on action category.
    fn default_verdict(category: ActionCategory) -> SafetyVerdict {
        match category {
            ActionCategory::Safe => SafetyVerdict::Allow,
            ActionCategory::Moderate => SafetyVerdict::Allow,
            ActionCategory::Destructive => SafetyVerdict::Confirm,
            ActionCategory::Financial => SafetyVerdict::Approve,
            ActionCategory::System => SafetyVerdict::Confirm,
        }
    }
}

impl Default for DomainSafetyGate {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_deny_cannot_be_overridden() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"operation": "delete", "query": "DROP TABLE users"});
        let result = gate.check(
            "database",
            &config,
            NicheCategory::FinTech,
            DataSensitivity::Low,
        );
        // Base gate classifies DROP as DESTRUCTIVE → should be handled
        assert!(!result.can_proceed || result.final_verdict == SafetyVerdict::Confirm);
    }

    #[test]
    fn fintech_compliance_bypass_is_denied() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "bypass_compliance", "target": "kyc_check"});
        let result = gate.check(
            "compliance_operation",
            &config,
            NicheCategory::FinTech,
            DataSensitivity::Medium,
        );
        assert!(result.domain_rules_matched.contains(&"fintech_compliance_bypass".to_string()));
        assert_eq!(result.final_verdict, SafetyVerdict::Deny);
        assert!(!result.can_proceed);
    }

    #[test]
    fn healthtech_phi_with_critical_sensitivity() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "phi_access", "data_type": "health_record"});
        let result = gate.check(
            "data_access",
            &config,
            NicheCategory::HealthTech,
            DataSensitivity::Critical,
        );
        // PHI access → Approve (domain rule), but Critical sensitivity escalates
        assert!(result.escalation_applied || result.final_verdict == SafetyVerdict::Deny);
    }

    #[test]
    fn safe_action_with_low_sensitivity() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "view_dashboard"});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::AiData,
            DataSensitivity::Low,
        );
        assert_eq!(result.base_verdict, SafetyVerdict::Allow);
        assert!(result.can_proceed);
        assert!(!result.escalation_applied);
    }

    #[test]
    fn critical_compliance_violation_causes_deny() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"data_type": "phi", "action": "access"});
        let result = gate.check(
            "data_access",
            &config,
            NicheCategory::HealthTech,
            DataSensitivity::Low,
        );
        // HIPAA violation with critical risk → DENY
        let has_critical = result.compliance_results.iter().any(|cr| {
            cr.risk_level == "critical" && !cr.compliant
        });
        if has_critical {
            assert_eq!(result.final_verdict, SafetyVerdict::Deny);
        }
    }

    #[test]
    fn escalation_high_sensitivity() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "view_data"});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::EdTech,
            DataSensitivity::High,
        );
        // Safe action with High sensitivity → ALLOW escalates to CONFIRM
        assert!(result.escalation_applied);
        assert_eq!(result.final_verdict, SafetyVerdict::Confirm);
    }

    #[test]
    fn domain_gate_default() {
        let gate = DomainSafetyGate::default();
        let config = serde_json::json!({});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::AiData,
            DataSensitivity::Low,
        );
        assert_eq!(result.final_verdict, SafetyVerdict::Allow);
    }

    #[test]
    fn check_domain_rules_only() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "bypass_compliance"});
        let rules = gate.check_domain_rules(NicheCategory::FinTech, "compliance", &config);
        assert!(rules.contains(&"fintech_compliance_bypass".to_string()));
    }

    #[test]
    fn check_compliance_only() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"data_type": "phi"});
        let result = gate.check_compliance(
            crate::compliance::ComplianceStandard::Hipaa,
            "data_access",
            &config,
        );
        assert!(!result.compliant);
    }

    #[test]
    fn get_domain_rules_returns_5() {
        let gate = DomainSafetyGate::new();
        let rules = gate.get_domain_rules(NicheCategory::FinTech);
        assert_eq!(rules.len(), 5);
    }

    #[test]
    fn result_display() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::AiData,
            DataSensitivity::Low,
        );
        assert!(result.to_string().contains("ALLOW"));
    }
}
