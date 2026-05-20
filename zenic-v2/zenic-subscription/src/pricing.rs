//! Pricing engine: cost calculations, tier comparison, and recommendations.
//!
//! All prices are in **USDT TRC20** only.

use crate::errors::SubscriptionError;
use crate::types::{AddOn, SubscriptionTier, SubscriptionTierName};

// ---------------------------------------------------------------------------
// PricingEngine
// ---------------------------------------------------------------------------

/// Calculates pricing for subscriptions, add-ons, and upgrades.
///
/// All monetary values are in **USDT TRC20**.
/// Annual billing gives 2 months free (10x monthly price).
pub struct PricingEngine;

impl PricingEngine {
    /// Calculates the monthly cost for a tier with optional add-ons.
    pub fn calculate_monthly_cost(
        tier: SubscriptionTierName,
        add_on_ids: &[String],
    ) -> u64 {
        let tier_price = tier.monthly_price_usdt();
        let add_on_cost: u64 = AddOn::all()
            .iter()
            .filter(|a| add_on_ids.contains(&a.id))
            .map(|a| a.monthly_price_usdt)
            .sum();
        tier_price + add_on_cost
    }

    /// Calculates the annual cost for a tier with optional add-ons.
    /// Annual billing: 10 months (2 months free).
    pub fn calculate_annual_cost(
        tier: SubscriptionTierName,
        add_on_ids: &[String],
    ) -> u64 {
        Self::calculate_monthly_cost(tier, add_on_ids) * 10
    }

    /// Calculates the one-time setup fee for a tier.
    pub fn calculate_setup_fee(tier: SubscriptionTierName) -> u64 {
        tier.setup_fee_usdt()
    }

    /// Calculates the total first-payment cost (setup + first month).
    pub fn calculate_first_payment(
        tier: SubscriptionTierName,
        add_on_ids: &[String],
    ) -> u64 {
        let setup = Self::calculate_setup_fee(tier);
        let monthly = Self::calculate_monthly_cost(tier, add_on_ids);
        setup + monthly
    }

    /// Calculates the prorated cost for an upgrade.
    ///
    /// Returns the amount to charge for the remaining days in the current period.
    pub fn calculate_upgrade_proration(
        from_tier: SubscriptionTierName,
        to_tier: SubscriptionTierName,
        days_remaining: u32,
        _days_in_period: u32,
    ) -> u64 {
        if !to_tier.is_upgrade_from(&from_tier) {
            return 0;
        }

        let from_daily = from_tier.monthly_price_usdt() as f64 / 30.0;
        let to_daily = to_tier.monthly_price_usdt() as f64 / 30.0;
        let daily_difference = to_daily - from_daily;

        (daily_difference * days_remaining as f64).ceil() as u64
    }

    /// Compares two tiers side by side.
    pub fn compare_tiers(
        tier_a: SubscriptionTierName,
        tier_b: SubscriptionTierName,
    ) -> TierComparison {
        let a = SubscriptionTier::for_name(tier_a);
        let b = SubscriptionTier::for_name(tier_b);

        TierComparison {
            tier_a: a,
            tier_b: b,
            price_difference_usdt: if tier_b.rank() > tier_a.rank() {
                tier_b.monthly_price_usdt() as i64 - tier_a.monthly_price_usdt() as i64
            } else {
                tier_a.monthly_price_usdt() as i64 - tier_b.monthly_price_usdt() as i64
            },
        }
    }

    /// Recommends a tier based on expected usage.
    pub fn recommend_tier(
        expected_workflows: u32,
        expected_actions_per_day: u32,
        expected_team_members: u32,
        needs_policy_engine: bool,
        needs_hitl: bool,
    ) -> SubscriptionTierName {
        // On-Premise Enterprise: if they need self-hosted
        if needs_hitl && needs_policy_engine && expected_team_members > 100 {
            return SubscriptionTierName::OnPremiseEnterprise;
        }

        // Enterprise: unlimited or HITL
        if needs_hitl
            || expected_workflows > 25
            || expected_actions_per_day > 1000
            || expected_team_members > 15
        {
            return SubscriptionTierName::Enterprise;
        }

        // Business: advanced features
        if expected_workflows > 5
            || expected_actions_per_day > 100
            || expected_team_members > 3
            || needs_policy_engine
        {
            return SubscriptionTierName::Business;
        }

        // Starter: basic usage
        SubscriptionTierName::Starter
    }

    /// Formats a pricing report for a tier.
    pub fn format_pricing_report(tier: SubscriptionTierName, add_on_ids: &[String]) -> String {
        let tier_def = SubscriptionTier::for_name(tier);
        let monthly = Self::calculate_monthly_cost(tier, add_on_ids);
        let annual = Self::calculate_annual_cost(tier, add_on_ids);
        let setup = Self::calculate_setup_fee(tier);
        let first_payment = Self::calculate_first_payment(tier, add_on_ids);

        let mut report = format!(
            "=== Pricing Report: {} ===\n\
             Monthly: {} USDT (TRC20)\n\
             Annual: {} USDT (TRC20) — 2 months free\n\
             Setup Fee: {} USDT (TRC20)\n\
             First Payment: {} USDT (TRC20)\n\
             \n\
             Features:\n",
            tier.display_name(),
            monthly,
            annual,
            setup,
            first_payment,
        );

        for feature in &tier_def.features {
            report.push_str(&format!("  ✓ {}\n", feature));
        }

        if !add_on_ids.is_empty() {
            report.push_str("\nAdd-ons:\n");
            for add_on in AddOn::all() {
                if add_on_ids.contains(&add_on.id) {
                    report.push_str(&format!(
                        "  + {} ({} USDT/mo)\n",
                        add_on.name, add_on.monthly_price_usdt
                    ));
                }
            }
        }

        report
    }

    /// Validates that a payment amount matches the expected cost.
    pub fn validate_payment_amount(
        expected_usdt: u64,
        received_usdt: u64,
        tolerance_percent: f64,
    ) -> Result<(), SubscriptionError> {
        let tolerance = expected_usdt as f64 * (tolerance_percent / 100.0);
        let difference = (expected_usdt as f64 - received_usdt as f64).abs();

        if difference > tolerance {
            return Err(SubscriptionError::PaymentAmountMismatch {
                expected: expected_usdt,
                actual: received_usdt,
            });
        }

        Ok(())
    }
}

// ---------------------------------------------------------------------------
// TierComparison
// ---------------------------------------------------------------------------

/// Result of comparing two tiers side by side.
#[derive(Debug, Clone)]
pub struct TierComparison {
    /// First tier in the comparison.
    pub tier_a: SubscriptionTier,
    /// Second tier in the comparison.
    pub tier_b: SubscriptionTier,
    /// Price difference in USDT (positive if tier_b is more expensive).
    pub price_difference_usdt: i64,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn monthly_cost_tier_only() {
        assert_eq!(
            PricingEngine::calculate_monthly_cost(SubscriptionTierName::Starter, &[]),
            29
        );
        assert_eq!(
            PricingEngine::calculate_monthly_cost(SubscriptionTierName::Business, &[]),
            99
        );
    }

    #[test]
    fn monthly_cost_with_add_ons() {
        let add_ons = vec!["extra_workflows_10".to_string()];
        let cost = PricingEngine::calculate_monthly_cost(SubscriptionTierName::Starter, &add_ons);
        assert_eq!(cost, 29 + 10);
    }

    #[test]
    fn annual_cost() {
        let annual = PricingEngine::calculate_annual_cost(SubscriptionTierName::Business, &[]);
        assert_eq!(annual, 990); // 99 * 10
    }

    #[test]
    fn setup_fee_on_premise() {
        let fee = PricingEngine::calculate_setup_fee(SubscriptionTierName::OnPremiseEnterprise);
        assert_eq!(fee, 2000);
    }

    #[test]
    fn first_payment_on_premise() {
        let first = PricingEngine::calculate_first_payment(
            SubscriptionTierName::OnPremiseEnterprise,
            &[],
        );
        assert_eq!(first, 2000 + 799); // setup + first month
    }

    #[test]
    fn upgrade_proration() {
        let proration = PricingEngine::calculate_upgrade_proration(
            SubscriptionTierName::Starter,
            SubscriptionTierName::Business,
            15,
            30,
        );
        let expected: u64 = ((99.0_f64 - 29.0_f64) / 30.0_f64 * 15.0_f64).ceil() as u64;
        assert_eq!(proration, expected);
    }

    #[test]
    fn recommend_tier_starter() {
        let tier = PricingEngine::recommend_tier(3, 50, 2, false, false);
        assert_eq!(tier, SubscriptionTierName::Starter);
    }

    #[test]
    fn recommend_tier_business() {
        let tier = PricingEngine::recommend_tier(10, 500, 5, true, false);
        assert_eq!(tier, SubscriptionTierName::Business);
    }

    #[test]
    fn recommend_tier_enterprise() {
        let tier = PricingEngine::recommend_tier(30, 2000, 20, true, false);
        assert_eq!(tier, SubscriptionTierName::Enterprise);
    }

    #[test]
    fn validate_payment_amount_exact() {
        assert!(PricingEngine::validate_payment_amount(99, 99, 0.0).is_ok());
    }

    #[test]
    fn validate_payment_amount_within_tolerance() {
        assert!(PricingEngine::validate_payment_amount(99, 98, 2.0).is_ok());
    }

    #[test]
    fn validate_payment_amount_outside_tolerance() {
        assert!(PricingEngine::validate_payment_amount(99, 50, 1.0).is_err());
    }

    #[test]
    fn compare_tiers() {
        let comparison = PricingEngine::compare_tiers(
            SubscriptionTierName::Starter,
            SubscriptionTierName::Business,
        );
        assert_eq!(comparison.price_difference_usdt, 70); // 99 - 29
    }
}
