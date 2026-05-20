// ─── Feature & Usage Check WASM Exports ────────────────────────────────────

use wasm_bindgen::prelude::*;
use types::*;

#[wasm_bindgen]
pub fn check_feature(tier_name: &str, feature_name: &str) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown tier: {}", tier_name), "available": false}).to_string(),
    };

    let feature: Feature = match serde_json::from_str::<Feature>(&format!("\"{}\"", feature_name)) {
        Ok(f) => f,
        Err(_) => return serde_json::json!({"error": format!("Unknown feature: {}", feature_name), "available": false}).to_string(),
    };

    let available = feature_available(tier, feature);
    let all_tiers = SubscriptionTier::all_tiers();
    let min_tier_name = all_tiers.iter().find(|t| feature_available(**t, feature)).map(|t| t.as_str().to_string());

    serde_json::json!({
        "feature": feature_name,
        "tier": tier_name,
        "available": available,
        "minimum_tier": min_tier_name,
        "denial_reason": if available { serde_json::Value::Null } else { serde_json::Value::String(format!("Feature '{}' requires upgrade from '{}'", feature_name, tier.display_name())) },
    }).to_string()
}

#[wasm_bindgen]
pub fn get_tier_features(tier_name: &str) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown tier: {}", tier_name)}).to_string(),
    };

    let feature_names = [
        "McpToolExecution", "McpCustomTools", "McpToolRegistration", "McpRateLimiting",
        "McpAuthApiKey", "McpAuthOAuth2", "McpAuthMTls", "McpMerkleAudit",
        "RbacBasicRoles", "RbacCustomRoles", "RbacDangerousPermApproval", "RbacSsoIntegration",
        "ObservabilityTracing", "ObservabilityBusinessMetrics", "ObservabilitySecurityMetrics",
        "ObservabilityResilienceMetrics", "ObservabilityOtelExport", "ObservabilityJsonExport",
        "ObservabilityCustomDashboards",
        "PolicyDeclarativeYaml", "PolicyVersioning", "PolicyTesting", "PolicyHotReload",
        "PolicyComplianceMapping", "PolicyComposition", "PolicyConflictDetection",
        "PolicyConstraintSolver", "PolicySimulation", "PolicyNamespaces", "PolicyTemplates",
        "PolicyApprovalWorkflow", "PolicyImpactAnalysis", "PolicyZ3Solver",
        "PlaybookActivation", "PlaybookCustomYaml", "PlaybookRoiCalculator",
        "PlaybookOnboardingWizard", "PlaybookCertification", "PlaybookComplianceMap",
        "HitlApprovalWorkflow", "HitlDelegation", "HitlEscalation", "HitlUndoReversible",
        "HitlEvidence", "HitlJustification", "HitlSlaTracking", "HitlAutoApprove",
        "HitlExpiryAutoRevert",
        "AuditBasicLog", "AuditMerkleChain", "AuditComplianceExport",
        "ExecutorBasic", "ExecutorData", "ExecutorStorage", "ExecutorSecurity",
        "ExecutorAdvanced", "ExecutorQueue", "ExecutorMonitoring",
        "OnPremiseDeployment", "OnPremiseAirGap", "OnPremiseCustomBranding", "OnPremiseDataResidency",
    ];

    let all_tiers = SubscriptionTier::all_tiers();
    let all_features: Vec<serde_json::Value> = feature_names.iter().map(|name| {
        let feature: Feature = match serde_json::from_str::<Feature>(&format!("\"{}\"", name)) {
            Ok(f) => f,
            Err(_) => return serde_json::json!({"feature": name, "available": false}),
        };
        let available = feature_available(tier, feature);
        let min_tier = all_tiers.iter().find(|t| feature_available(**t, feature)).map(|t| t.as_str().to_string());
        serde_json::json!({ "feature": name, "available": available, "minimum_tier": min_tier })
    }).collect();

    serde_json::json!({
        "tier": tier_name,
        "display_name": tier.display_name(),
        "features": all_features,
        "payment_currency": "USDT",
        "payment_network": "TRC20",
    }).to_string()
}

#[wasm_bindgen]
pub fn check_usage(tier_name: &str, resource: &str, current_usage: u32) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown tier: {}", tier_name)}).to_string(),
    };

    let limits = TierLimits::for_tier(tier);
    let (max, overage_rate) = match resource {
        "workflows" => (limits.max_workflows, 0.0),
        "actions_per_day" => (limits.max_actions_per_day, limits.overage_rate_usdt),
        "policies" => (limits.max_policies, 0.0),
        "team_members" => (limits.max_team_members, 0.0),
        "mcp_tools" => (limits.max_mcp_tools, 0.0),
        "approval_requests_per_day" => (limits.max_approval_requests_per_day, limits.overage_rate_usdt),
        "playbooks" => (limits.max_playbooks, 0.0),
        "namespaces" => (limits.max_namespaces, 0.0),
        "simulations_per_month" => (limits.max_simulations_per_month, 0.0),
        _ => return serde_json::json!({"error": format!("Unknown resource: {}", resource)}).to_string(),
    };

    let allowed = max == 0 || current_usage <= max;
    let remaining = if max == 0 { 0 } else { max.saturating_sub(current_usage) };
    let overage = if max > 0 && current_usage > max { (current_usage - max) as f64 * overage_rate } else { 0.0 };
    let denial_reason = if !allowed && max > 0 {
        Some(format!("Usage {} exceeds limit {} for '{}' on {} tier. Upgrade required.", current_usage, max, resource, tier.display_name()))
    } else { None };

    let result = UsageCheckResult {
        resource: resource.to_string(),
        allowed,
        current_usage,
        max_allowed: max,
        remaining,
        overage_charge_usdt: overage,
        minimum_tier: None,
        feature_available: allowed,
        denial_reason,
    };

    serde_json::to_string(&result).unwrap_or_else(|_| "{}".to_string())
}
