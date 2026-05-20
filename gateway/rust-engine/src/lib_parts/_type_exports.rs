// ─── Type & Pricing WASM Exports ─────────────────────────────────────────
// Tier queries, pricing calculations, feature checks, usage limits,
// subscription management, and manual payment verification.

use crate::types::*;
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn engine_version() -> String {
    "3.1.0".to_string()
}

#[wasm_bindgen]
pub fn get_all_tiers() -> String {
    let tiers: Vec<serde_json::Value> = SubscriptionTier::all_tiers().iter().map(|t| {
        let limits = TierLimits::for_tier(*t);
        serde_json::json!({
            "name": t.as_str(),
            "display_name": t.display_name(),
            "monthly_price_usdt": t.monthly_price_usdt(),
            "annual_price_usdt": t.annual_price_usdt(),
            "setup_fee_usdt": t.setup_fee_usdt(),
            "recommended_for": t.recommended_for(),
            "limits": limits,
            "payment_currency": "USDT",
            "payment_network": "TRC20",
        })
    }).collect();
    serde_json::to_string(&tiers).unwrap_or_else(|_| "[]".to_string())
}

#[wasm_bindgen]
pub fn get_paid_tiers() -> String {
    let tiers: Vec<serde_json::Value> = SubscriptionTier::paid_tiers().iter().map(|t| {
        let limits = TierLimits::for_tier(*t);
        serde_json::json!({
            "name": t.as_str(),
            "display_name": t.display_name(),
            "monthly_price_usdt": t.monthly_price_usdt(),
            "annual_price_usdt": t.annual_price_usdt(),
            "setup_fee_usdt": t.setup_fee_usdt(),
            "recommended_for": t.recommended_for(),
            "limits": limits,
            "payment_currency": "USDT",
            "payment_network": "TRC20",
        })
    }).collect();
    serde_json::to_string(&tiers).unwrap_or_else(|_| "[]".to_string())
}

#[wasm_bindgen]
pub fn get_add_ons() -> String {
    let addons: Vec<serde_json::Value> = AddOn::all().iter().map(|a| {
        let tiers_owned = a.available_for_tiers();
        let tier_names: Vec<String> = tiers_owned.iter().map(|t| t.as_str().to_string()).collect();
        serde_json::json!({
            "id": format!("{:?}", a),
            "display_name": a.display_name(),
            "monthly_price_usdt": a.monthly_price_usdt(),
            "available_for_tiers": tier_names,
            "payment_currency": "USDT",
            "payment_network": "TRC20",
        })
    }).collect();
    serde_json::to_string(&addons).unwrap_or_else(|_| "[]".to_string())
}

#[wasm_bindgen]
pub fn get_trial_config() -> String {
    serde_json::to_string(&TrialConfig::default()).unwrap_or_else(|_| "{}".to_string())
}

#[wasm_bindgen]
pub fn calculate_pricing(tier_name: &str, add_ons_json: &str) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown tier: {}", tier_name)}).to_string(),
    };

    let add_ons: Vec<AddOn> = serde_json::from_str(add_ons_json).unwrap_or_default();
    let limits = TierLimits::for_tier(tier);
    let add_ons_monthly: f64 = add_ons.iter().map(|a| a.monthly_price_usdt()).sum();
    let monthly = tier.monthly_price_usdt();
    let annual = tier.annual_price_usdt();
    let setup = tier.setup_fee_usdt();

    let calc = PricingCalculation {
        tier,
        monthly_price_usdt: monthly,
        annual_price_usdt: annual,
        setup_fee_usdt: setup,
        add_ons_monthly_usdt: add_ons_monthly,
        total_first_month_usdt: monthly + setup + add_ons_monthly,
        total_monthly_recurring_usdt: monthly + add_ons_monthly,
        total_annual_usdt: annual + setup + (add_ons_monthly * 12.0),
        overage_rate_usdt: limits.overage_rate_usdt,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    };

    serde_json::to_string(&calc).unwrap_or_else(|_| "{}".to_string())
}

#[wasm_bindgen]
pub fn compare_tiers(estimated_actions_per_month: u32, add_ons_json: &str) -> String {
    let add_ons: Vec<AddOn> = serde_json::from_str(add_ons_json).unwrap_or_default();
    let add_ons_monthly: f64 = add_ons.iter().map(|a| a.monthly_price_usdt()).sum();

    let tier_calcs: Vec<PricingCalculation> = SubscriptionTier::paid_tiers().iter().map(|t| {
        let limits = TierLimits::for_tier(*t);
        let monthly = t.monthly_price_usdt();
        PricingCalculation {
            tier: *t,
            monthly_price_usdt: monthly,
            annual_price_usdt: t.annual_price_usdt(),
            setup_fee_usdt: t.setup_fee_usdt(),
            add_ons_monthly_usdt: add_ons_monthly,
            total_first_month_usdt: monthly + t.setup_fee_usdt() + add_ons_monthly,
            total_monthly_recurring_usdt: monthly + add_ons_monthly,
            total_annual_usdt: t.annual_price_usdt() + t.setup_fee_usdt() + (add_ons_monthly * 12.0),
            overage_rate_usdt: limits.overage_rate_usdt,
            payment_currency: "USDT".to_string(),
            payment_network: "TRC20".to_string(),
        }
    }).collect();

    let (recommended, reason) = if estimated_actions_per_month < 500 {
        (SubscriptionTier::Starter, format!("Con {} acciones/mes, Starter ofrece el mejor valor.", estimated_actions_per_month))
    } else if estimated_actions_per_month <= 5000 {
        (SubscriptionTier::Business, format!("Con {} acciones/mes, Business es la elección óptima.", estimated_actions_per_month))
    } else if estimated_actions_per_month <= 50000 {
        (SubscriptionTier::Enterprise, format!("Con {} acciones/mes, Enterprise maximiza el ROI.", estimated_actions_per_month))
    } else {
        (SubscriptionTier::OnPremiseEnterprise, format!("Con {} acciones/mes, On-Premise Enterprise es la solución.", estimated_actions_per_month))
    };

    let comparison = TierComparison {
        tiers: tier_calcs,
        recommended_tier: recommended,
        recommendation_reason: reason,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    };

    serde_json::to_string(&comparison).unwrap_or_else(|_| "{}".to_string())
}

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

#[wasm_bindgen]
pub fn get_tier_limits(tier_name: &str) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown tier: {}", tier_name)}).to_string(),
    };
    serde_json::to_string(&TierLimits::for_tier(tier)).unwrap_or_else(|_| "{}".to_string())
}

#[wasm_bindgen]
pub fn validate_trc20_address(address: &str) -> String {
    let valid = address.starts_with('T') && address.len() == 34 && address[1..].chars().all(|c| c.is_alphanumeric());
    serde_json::json!({
        "address": address,
        "valid": valid,
        "network": "TRC20",
        "currency": "USDT",
        "reason": if valid { "Valid TRC20 address format" } else { "TRC20 address must start with 'T' and be 34 characters alphanumeric" },
    }).to_string()
}

#[wasm_bindgen]
pub fn create_trial_subscription(tenant_id: &str, email: &str) -> String {
    let config = TrialConfig::default();
    let subscription = Subscription {
        id: format!("sub_trial_{}", sha256_short(&format!("{}:{}", tenant_id, email))),
        tenant_id: tenant_id.to_string(),
        tier: SubscriptionTier::Trial,
        status: SubscriptionStatus::Trial,
        payment_method: PaymentMethod::UsdtTrc20,
        billing_wallet: String::new(),
        add_ons: vec![],
        started_at: chrono_now_iso(),
        current_period_end: chrono_future_iso(config.duration_days as i64),
        trial_ends_at: Some(chrono_future_iso(config.duration_days as i64)),
        auto_renew: false,
        last_payment_tx_hash: None,
        cancelled_at: None,
        cancellation_reason: None,
    };

    serde_json::json!({
        "subscription": subscription,
        "trial_config": config,
        "mandatory_for_all": true,
        "trial_is_prerequisite": true,
        "message": format!("Trial de {} días activado. Acceso completo al Plan Business.", config.duration_days),
        "payment_required": false,
        "payment_currency": "USDT",
        "payment_network": "TRC20",
    }).to_string()
}

#[wasm_bindgen]
pub fn convert_trial_to_paid(tenant_id: &str, tier_name: &str, wallet_address: &str) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) if t != SubscriptionTier::Trial => t,
        _ => return serde_json::json!({"error": "Must convert to a paid tier"}).to_string(),
    };

    let wallet_valid = wallet_address.starts_with('T') && wallet_address.len() == 34;
    if !wallet_valid {
        return serde_json::json!({"error": "Invalid TRC20 wallet address"}).to_string();
    }

    let monthly = tier.monthly_price_usdt();
    let setup = tier.setup_fee_usdt();
    let first_payment = monthly + setup;

    let subscription = Subscription {
        id: format!("sub_{}", sha256_short(&format!("{}:{}", tenant_id, tier_name))),
        tenant_id: tenant_id.to_string(),
        tier,
        status: SubscriptionStatus::Active,
        payment_method: PaymentMethod::UsdtTrc20,
        billing_wallet: wallet_address.to_string(),
        add_ons: vec![],
        started_at: chrono_now_iso(),
        current_period_end: chrono_future_iso(30),
        trial_ends_at: None,
        auto_renew: true,
        last_payment_tx_hash: None,
        cancelled_at: None,
        cancellation_reason: None,
    };

    serde_json::json!({
        "subscription": subscription,
        "payment_required": first_payment,
        "payment_currency": "USDT",
        "payment_network": "TRC20",
        "breakdown": { "monthly_usdt": monthly, "setup_fee_usdt": setup, "first_payment_usdt": first_payment },
        "message": format!("Suscripción {} activada. Pago de {} USDT (TRC20) requerido.", tier.display_name(), first_payment),
    }).to_string()
}

// ─── Manual Payment Verification Functions ────────────────────────────────

#[wasm_bindgen]
pub fn get_payment_verification_methods() -> String {
    let methods = vec![
        serde_json::json!({
            "id": "manual_admin",
            "display_name": "Verificación Manual por Admin",
            "description": "Un administrador verifica manualmente el pago USDT TRC20",
            "currency": "USDT",
            "network": "TRC20",
        }),
        serde_json::json!({
            "id": "semi_manual_onchain",
            "display_name": "Verificación Semi-Manual On-Chain",
            "description": "El sistema verifica on-chain, un admin aprueba",
            "currency": "USDT",
            "network": "TRC20",
        }),
    ];
    serde_json::to_string(&methods).unwrap_or_else(|_| "[]".to_string())
}

#[wasm_bindgen]
pub fn is_trial_mandatory() -> String {
    let config = TrialConfig::default();
    serde_json::json!({
        "mandatory_for_all": config.mandatory_for_all,
        "trial_is_prerequisite": config.trial_is_prerequisite,
        "duration_days": config.duration_days,
        "granted_tier": config.granted_tier.as_str(),
        "message": "Todos los usuarios deben iniciar con el trial de 14 días del Plan Business. No se puede saltar al pago directamente.",
        "payment_currency": "USDT",
        "payment_network": "TRC20",
    }).to_string()
}

#[wasm_bindgen]
pub fn create_manual_payment_request(subscription_id: &str, amount_usdt: f64, wallet_from: &str, platform_wallet: &str) -> String {
    let verification = ManualPaymentVerification {
        payment_id: format!("pay_{}", sha256_short(&format!("{}:{}:{}", subscription_id, amount_usdt, wallet_from))),
        subscription_id: subscription_id.to_string(),
        amount_usdt,
        wallet_from: wallet_from.to_string(),
        wallet_to: platform_wallet.to_string(),
        tx_hash: None,
        verification_method: PaymentVerificationMethod::ManualAdmin,
        status: ManualPaymentStatus::AwaitingPayment,
        admin_notes: None,
        confirmed_by: None,
        confirmed_at: None,
        created_at: chrono_now_iso(),
    };

    serde_json::json!({
        "payment_request": verification,
        "instructions": {
            "step1": "Envía exactamente {amount_usdt} USDT por la red TRC20 a la wallet del platform",
            "step2": "Copia el hash de la transacción TRC20",
            "step3": "Proporciona el tx_hash para verificación manual por admin",
            "step4": "Un administrador confirmará tu pago manualmente",
        },
        "platform_wallet": platform_wallet,
        "amount_usdt": amount_usdt,
        "payment_currency": "USDT",
        "payment_network": "TRC20",
        "estimated_confirmation_time": "1-24 horas (verificación manual por admin)",
    }).to_string()
}

#[wasm_bindgen]
pub fn confirm_manual_payment(payment_id: &str, tx_hash: &str, confirmed_by: &str) -> String {
    // Validate tx hash format
    let tx_valid = tx_hash.len() == 64 && tx_hash.chars().all(|c| c.is_ascii_hexdigit());

    if !tx_valid {
        return serde_json::json!({
            "error": "Invalid TRC20 transaction hash",
            "details": "TRC20 tx hash must be 64 hex characters",
        }).to_string();
    }

    serde_json::json!({
        "payment_id": payment_id,
        "tx_hash": tx_hash,
        "status": "awaiting_confirmation",
        "confirmed_by": confirmed_by,
        "message": "Pago registrado. Un administrador debe confirmar manualmente la recepción del USDT TRC20.",
        "payment_currency": "USDT",
        "payment_network": "TRC20",
    }).to_string()
}

// ─── Internal Helpers ──────────────────────────────────────────────────────

fn sha256_short(input: &str) -> String {
    use sha2::{Sha256, Digest};
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    format!("{:x}", hasher.finalize())[..12].to_string()
}

fn chrono_now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

fn chrono_future_iso(days: i64) -> String {
    (chrono::Utc::now() + chrono::Duration::days(days)).to_rfc3339()
}
