// ─── Pricing WASM Exports ────────────────────────────────────────────────

use wasm_bindgen::prelude::*;
use types::*;

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
pub fn get_tier_limits(tier_name: &str) -> String {
    let tier = match SubscriptionTier::from_str_value(tier_name) {
        Some(t) => t,
        None => return serde_json::json!({"error": format!("Unknown tier: {}", tier_name)}).to_string(),
    };
    serde_json::to_string(&TierLimits::for_tier(tier)).unwrap_or_else(|_| "{}".to_string())
}
