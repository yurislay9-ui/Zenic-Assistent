//! Subscription engine tests.

#[cfg(test)]
mod tests {
    use super::super::impl::SubscriptionEngine;
    use crate::payment::UsdtPaymentMethod;
    use crate::types::{SubscriptionStatus, SubscriptionTierName};
    use crate::usage::UsageType;
    use zenic_proto::TenantId;

    fn make_engine() -> SubscriptionEngine {
        SubscriptionEngine::new(
            "TCompanyWallet1234567890abcdefghijk".to_string(),
            UsdtPaymentMethod::Manual,
        )
    }

    #[test]
    fn engine_signup() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        let subscription = engine.signup(tenant, 1000).expect("signup");

        assert_eq!(subscription.status, SubscriptionStatus::Trial);
        assert_eq!(subscription.tier, SubscriptionTierName::Business);
        assert!(subscription.has_access());
        assert_eq!(engine.active_trial_count(), 1);
    }

    #[test]
    fn engine_signup_and_pay() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        // Signup.
        engine.signup(tenant, 1000).expect("signup");

        // Create payment.
        let payment = engine.create_payment(tenant, SubscriptionTierName::Business, &[], 2000).expect("create payment");
        assert_eq!(payment.amount_usdt, 99); // Business: $99/mo

        // Submit tx hash.
        engine.submit_payment_tx(
            payment.id,
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2".to_string(),
            "TXYZabcd1234abcd1234abcd1234abcd12".to_string(),
            12345,
        ).expect("submit tx");

        // Confirm payment.
        let subscription = engine.confirm_payment(
            payment.id,
            "admin".to_string(),
            Some("Verified".to_string()),
            3000,
        ).expect("confirm payment");

        assert_eq!(subscription.status, SubscriptionStatus::Active);
        assert_eq!(subscription.tier, SubscriptionTierName::Business);
    }

    #[test]
    fn engine_cancel_subscription() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        engine.signup(tenant, 1000).expect("signup");

        // Manually set to Active for testing cancellation.
        let sub = engine.subscriptions.get_mut(&tenant).unwrap();
        sub.transition_to(SubscriptionStatus::Active).expect("transition");

        let subscription = engine.cancel_subscription(tenant, 5000).expect("cancel");

        assert_eq!(subscription.status, SubscriptionStatus::Cancelled);
        assert!(!subscription.has_access());
    }

    #[test]
    fn engine_check_feature() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        engine.signup(tenant, 1000).expect("signup");

        // Business tier features.
        assert!(engine.check_feature(tenant, "thinking_engine"));
        assert!(engine.check_feature(tenant, "basic_pipeline"));

        // Enterprise-only features.
        assert!(!engine.check_feature(tenant, "mcp_gateway"));
    }

    #[test]
    fn engine_usage_metering() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        engine.signup(tenant, 1000).expect("signup");

        // Business tier: 25 workflows.
        assert!(engine.record_usage(tenant, UsageType::Workflows, 5, 2000).is_ok());
        assert!(engine.check_usage_limit(tenant, UsageType::Workflows, 20).is_ok());
        assert!(engine.check_usage_limit(tenant, UsageType::Workflows, 21).is_err());
    }

    #[test]
    fn engine_trial_expiration() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        engine.signup(tenant, 1000).expect("signup");

        // Expire the trial (14 days later).
        let expired = engine.check_trial_expirations(1000 + crate::trial::TRIAL_DURATION_MS);
        assert_eq!(expired.len(), 1);

        let subscription = engine.get_subscription(&tenant).expect("subscription");
        assert_eq!(subscription.status, SubscriptionStatus::Expired);
    }

    #[test]
    fn engine_company_wallet() {
        let engine = make_engine();
        assert!(engine.company_wallet().starts_with('T'));
    }

    #[test]
    fn engine_on_premise_payment() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        engine.signup(tenant, 1000).expect("signup");

        // Create payment for On-Premise Enterprise.
        let payment = engine.create_payment(
            tenant,
            SubscriptionTierName::OnPremiseEnterprise,
            &[],
            2000,
        ).expect("create payment");

        // Should include setup fee: $799 + $2,000 = $2,799
        assert_eq!(payment.amount_usdt, 2799);
        assert!(payment.includes_setup_fee);
        assert_eq!(payment.setup_fee_amount_usdt, 2000);
    }
}
