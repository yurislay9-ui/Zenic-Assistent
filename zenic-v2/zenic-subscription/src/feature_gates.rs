//! Feature gates: per-tier feature access control.
//!
//! Feature gates map subscription tiers to available features.
//! Used by middleware to block features that are not available in the user's tier.

use crate::types::SubscriptionTierName;

// ---------------------------------------------------------------------------
// FeatureGate
// ---------------------------------------------------------------------------

/// A feature gate defines whether a feature is available for a given tier.
#[derive(Debug, Clone, PartialEq)]
pub struct FeatureGate {
    /// Feature identifier (e.g., "mcp_gateway", "hitl_approvals").
    pub feature: String,
    /// Human-readable description.
    pub description: String,
    /// Minimum tier required for this feature.
    pub minimum_tier: SubscriptionTierName,
    /// Whether this feature is available as an add-on.
    pub available_as_addon: bool,
    /// Add-on ID that provides this feature (if available as add-on).
    pub addon_id: Option<String>,
}

impl FeatureGate {
    /// Creates a new feature gate.
    pub fn new(
        feature: &str,
        description: &str,
        minimum_tier: SubscriptionTierName,
    ) -> Self {
        Self {
            feature: feature.to_string(),
            description: description.to_string(),
            minimum_tier,
            available_as_addon: false,
            addon_id: None,
        }
    }

    /// Creates a feature gate that is available as an add-on.
    pub fn with_addon(
        feature: &str,
        description: &str,
        minimum_tier: SubscriptionTierName,
        addon_id: &str,
    ) -> Self {
        Self {
            feature: feature.to_string(),
            description: description.to_string(),
            minimum_tier,
            available_as_addon: true,
            addon_id: Some(addon_id.to_string()),
        }
    }

    /// Checks if this feature is available for the given tier (considering add-ons).
    pub fn is_available(&self, tier: SubscriptionTierName, active_addons: &[String]) -> bool {
        // Check if tier meets the minimum requirement.
        if tier.rank() >= self.minimum_tier.rank() {
            return true;
        }

        // Check if the feature is available via an add-on.
        if self.available_as_addon {
            if let Some(ref addon_id) = self.addon_id {
                return active_addons.contains(addon_id);
            }
        }

        false
    }

    /// Returns all feature gates for the Zenic-Agents platform.
    ///
    /// Maps all 70+ API routes and 19 executors to their tier requirements.
    pub fn all_gates() -> Vec<FeatureGate> {
        vec![
            // === Core Pipeline ===
            FeatureGate::new("basic_pipeline", "Basic IA pipeline (L1-L4)", SubscriptionTierName::Starter),
            FeatureGate::new("full_pipeline", "Full 8-level IA pipeline (L1-L8)", SubscriptionTierName::Business),
            FeatureGate::new("chat_completions", "Chat completion API", SubscriptionTierName::Starter),
            FeatureGate::new("app_generation", "Application generation", SubscriptionTierName::Business),
            FeatureGate::new("automation_generation", "Automation generation", SubscriptionTierName::Business),
            FeatureGate::new("schema_design", "Schema design tools", SubscriptionTierName::Business),
            FeatureGate::new("thinking_engine", "Thinking engine (advanced reasoning)", SubscriptionTierName::Business),
            FeatureGate::new("reasoning_engine", "Reasoning engine (deep analysis)", SubscriptionTierName::Business),
            FeatureGate::new("logic_chains", "Logic chain builder", SubscriptionTierName::Business),

            // === MCP Gateway (Phase 1) ===
            FeatureGate::new("mcp_gateway", "MCP Protocol Gateway", SubscriptionTierName::Enterprise),
            FeatureGate::new("mcp_tools_register", "Register custom MCP tools", SubscriptionTierName::Enterprise),
            FeatureGate::new("mcp_rate_limit_custom", "Custom rate limit algorithms", SubscriptionTierName::Enterprise),
            FeatureGate::new("mcp_audit_full", "Full MCP audit trail", SubscriptionTierName::Enterprise),

            // === RBAC ===
            FeatureGate::new("rbac_basic", "Basic RBAC (3 roles)", SubscriptionTierName::Business),
            FeatureGate::new("rbac_full", "Full RBAC (18 permissions, custom roles)", SubscriptionTierName::Enterprise),
            FeatureGate::new("rbac_dangerous_actions", "Dangerous action approval flow", SubscriptionTierName::Enterprise),

            // === Observability (Phase 2) ===
            FeatureGate::with_addon("observability_basic", "Basic observability (traces, metrics)", SubscriptionTierName::Business, "advanced_analytics"),
            FeatureGate::new("observability_full", "Full observability (tracing, metrics, export, custom dashboards)", SubscriptionTierName::Enterprise),
            FeatureGate::new("observability_export", "Export traces/metrics to external systems", SubscriptionTierName::Enterprise),

            // === Playbooks (Phase 3) ===
            FeatureGate::new("playbook_library", "Access to playbook library", SubscriptionTierName::Business),
            FeatureGate::new("playbook_custom", "Create custom playbooks", SubscriptionTierName::Enterprise),
            FeatureGate::new("playbook_roi", "ROI calculation and tracking", SubscriptionTierName::Business),

            // === Policy Engine (Phase 4) ===
            FeatureGate::with_addon("policy_engine_basic", "Basic policy engine (10 rules)", SubscriptionTierName::Enterprise, "policy_engine"),
            FeatureGate::new("policy_engine_full", "Full policy engine (unlimited rules, Z3 solver, compliance mapping)", SubscriptionTierName::Enterprise),
            FeatureGate::new("policy_compliance_mapping", "Compliance mapping (30+ standards)", SubscriptionTierName::Enterprise),
            FeatureGate::new("policy_conflict_detection", "Conflict detection (Z3+AC-3 solver)", SubscriptionTierName::Enterprise),
            FeatureGate::new("policy_versioning", "Policy versioning and rollback", SubscriptionTierName::Enterprise),
            FeatureGate::new("policy_simulation", "Policy simulation and impact analysis", SubscriptionTierName::Enterprise),

            // === HITL (Phase 5) ===
            FeatureGate::with_addon("hitl_approvals", "Human-in-the-loop approval chains", SubscriptionTierName::Business, "hitl_approvals"),
            FeatureGate::new("hitl_reversible_actions", "Reversible actions (Memento pattern)", SubscriptionTierName::Enterprise),
            FeatureGate::new("hitl_delegation", "Approval delegation", SubscriptionTierName::Enterprise),
            FeatureGate::new("hitl_escalation", "Escalation workflows", SubscriptionTierName::Enterprise),
            FeatureGate::new("hitl_evidence", "Evidence collection for approvals", SubscriptionTierName::Enterprise),
            FeatureGate::new("hitl_sla_tracking", "SLA tracking for approval chains", SubscriptionTierName::Enterprise),

            // === 19 Action Executors ===
            FeatureGate::new("executor_basic", "Basic executors (file, shell, http)", SubscriptionTierName::Starter),
            FeatureGate::new("executor_advanced", "Advanced executors (db, api, transform)", SubscriptionTierName::Business),
            FeatureGate::new("executor_all", "All 19 executors including Merkle Ledger", SubscriptionTierName::Enterprise),

            // === Merkle Audit ===
            FeatureGate::new("merkle_audit", "Merkle tree audit logging", SubscriptionTierName::Enterprise),

            // === Verdict Engine ===
            FeatureGate::new("verdict_basic", "Deterministic pipeline verdicts", SubscriptionTierName::Starter),
            FeatureGate::new("verdict_consensus", "Consensus resolver + evidence collector", SubscriptionTierName::Business),
            FeatureGate::new("verdict_full", "Full 4-layer verdict architecture", SubscriptionTierName::Enterprise),

            // === Self-Hosted / On-Premise ===
            FeatureGate::new("self_hosted", "Self-hosted deployment", SubscriptionTierName::OnPremiseEnterprise),
            FeatureGate::new("white_label", "White-label branding", SubscriptionTierName::OnPremiseEnterprise),
            FeatureGate::new("source_code_access", "Source code access", SubscriptionTierName::OnPremiseEnterprise),
            FeatureGate::new("custom_integrations", "Custom integration development", SubscriptionTierName::OnPremiseEnterprise),
            FeatureGate::new("air_gap", "Air-gap capable deployment", SubscriptionTierName::OnPremiseEnterprise),
            FeatureGate::new("military_encryption", "Military-grade encryption", SubscriptionTierName::OnPremiseEnterprise),

            // === API Rate Limits ===
            FeatureGate::new("api_rate_30", "30 API calls/minute", SubscriptionTierName::Starter),
            FeatureGate::new("api_rate_100", "100 API calls/minute", SubscriptionTierName::Business),
            FeatureGate::new("api_rate_1000", "1000 API calls/minute", SubscriptionTierName::Enterprise),
            FeatureGate::new("api_rate_unlimited", "Unlimited API calls", SubscriptionTierName::OnPremiseEnterprise),

            // === Support ===
            FeatureGate::new("community_support", "Community support", SubscriptionTierName::Starter),
            FeatureGate::new("priority_support", "Priority support", SubscriptionTierName::Business),
            FeatureGate::new("dedicated_support", "Dedicated support engineer", SubscriptionTierName::Enterprise),
            FeatureGate::new("dedicated_engineer", "Dedicated on-site engineer", SubscriptionTierName::OnPremiseEnterprise),

            // === SLA ===
            FeatureGate::new("sla_standard", "Standard SLA (99.5%)", SubscriptionTierName::Starter),
            FeatureGate::new("sla_high", "High availability SLA (99.9%)", SubscriptionTierName::Enterprise),
            FeatureGate::new("sla_custom", "Custom SLA", SubscriptionTierName::OnPremiseEnterprise),
        ]
    }

    /// Checks if a feature is available for a tier with optional add-ons.
    pub fn check_feature(
        feature: &str,
        tier: SubscriptionTierName,
        active_addons: &[String],
    ) -> bool {
        Self::all_gates()
            .iter()
            .find(|g| g.feature == feature)
            .map(|g| g.is_available(tier, active_addons))
            .unwrap_or(false) // Unknown features are blocked by default.
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn feature_gate_basic() {
        let gate = FeatureGate::new("basic_pipeline", "Basic pipeline", SubscriptionTierName::Starter);
        assert!(gate.is_available(SubscriptionTierName::Starter, &[]));
        assert!(gate.is_available(SubscriptionTierName::Business, &[]));
    }

    #[test]
    fn feature_gate_enterprise_only() {
        let gate = FeatureGate::new("mcp_gateway", "MCP Gateway", SubscriptionTierName::Enterprise);
        assert!(!gate.is_available(SubscriptionTierName::Starter, &[]));
        assert!(!gate.is_available(SubscriptionTierName::Business, &[]));
        assert!(gate.is_available(SubscriptionTierName::Enterprise, &[]));
    }

    #[test]
    fn feature_gate_with_addon() {
        let gate = FeatureGate::with_addon(
            "policy_engine_basic",
            "Basic policy engine",
            SubscriptionTierName::Enterprise,
            "policy_engine",
        );

        // Not available in Business without add-on.
        assert!(!gate.is_available(SubscriptionTierName::Business, &[]));

        // Available in Business with the add-on.
        assert!(gate.is_available(SubscriptionTierName::Business, &["policy_engine".to_string()]));

        // Available in Enterprise without add-on.
        assert!(gate.is_available(SubscriptionTierName::Enterprise, &[]));
    }

    #[test]
    fn check_feature_starter() {
        assert!(FeatureGate::check_feature("basic_pipeline", SubscriptionTierName::Starter, &[]));
        assert!(!FeatureGate::check_feature("thinking_engine", SubscriptionTierName::Starter, &[]));
        assert!(!FeatureGate::check_feature("mcp_gateway", SubscriptionTierName::Starter, &[]));
    }

    #[test]
    fn check_feature_business() {
        assert!(FeatureGate::check_feature("thinking_engine", SubscriptionTierName::Business, &[]));
        assert!(FeatureGate::check_feature("verdict_consensus", SubscriptionTierName::Business, &[]));
        assert!(!FeatureGate::check_feature("mcp_gateway", SubscriptionTierName::Business, &[]));
    }

    #[test]
    fn check_feature_with_addon() {
        assert!(FeatureGate::check_feature(
            "policy_engine_basic",
            SubscriptionTierName::Business,
            &["policy_engine".to_string()],
        ));
        assert!(!FeatureGate::check_feature(
            "policy_engine_basic",
            SubscriptionTierName::Business,
            &[],
        ));
    }

    #[test]
    fn check_feature_unknown_blocked() {
        assert!(!FeatureGate::check_feature("unknown_feature", SubscriptionTierName::Enterprise, &[]));
    }

    #[test]
    fn all_gates_count() {
        let gates = FeatureGate::all_gates();
        assert!(gates.len() >= 40, "Expected at least 40 feature gates, got {}", gates.len());
    }
}
