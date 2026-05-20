//! Subscription lifecycle: signup, payment, cancellation, renewal, and upgrade.

use zenic_proto::{PaymentId, TenantId};

use crate::errors::SubscriptionError;
use crate::feature_gates::FeatureGate;
use crate::payment::UsdtPayment;
use crate::pricing::PricingEngine;
use crate::saga::context::SagaContext;
use crate::saga::{CancellationSaga, PaymentSaga, RenewalSaga, SignupSaga, SubscriptionSaga, UpgradeSaga};
use crate::types::{Subscription, SubscriptionStatus, SubscriptionTierName};
use crate::usage::UsageType;

use super::types::SubscriptionEngine;

impl SubscriptionEngine {
    // -----------------------------------------------------------------------
    // Signup + Trial
    // -----------------------------------------------------------------------

    /// Signs up a new user with a 14-day Business trial.
    ///
    /// Uses the SignupSaga to ensure atomic signup:
    /// validate_user → create_trial → activate_trial → notify_user
    pub fn signup(&mut self, tenant_id: TenantId, now_ms: u64) -> Result<Subscription, SubscriptionError> {
        // Execute the signup saga.
        let mut ctx = SagaContext::new(tenant_id, SubscriptionTierName::Starter);
        let saga = SignupSaga;
        saga.execute(&mut ctx)?;

        // Create the trial.
        let trial = self.trial_manager.create_trial(tenant_id, now_ms)?;

        // Create the subscription in Trial state.
        let subscription = Subscription::new_trial(tenant_id, trial.id, now_ms);
        self.subscriptions.insert(tenant_id, subscription.clone());

        // Initialize usage metering for Business tier (trial).
        self.usage_meter.initialize_for_tenant(tenant_id, SubscriptionTierName::Business, now_ms);

        Ok(subscription)
    }

    // -----------------------------------------------------------------------
    // Payment
    // -----------------------------------------------------------------------

    /// Creates a pending USDT TRC20 payment for a subscription.
    pub fn create_payment(
        &mut self,
        tenant_id: TenantId,
        tier: SubscriptionTierName,
        add_on_ids: &[String],
        now_ms: u64,
    ) -> Result<UsdtPayment, SubscriptionError> {
        let subscription = self.subscriptions.get(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(
                self.subscriptions.get(&tenant_id).map(|s| s.id).unwrap_or_else(zenic_proto::SubscriptionId::new)
            )
        })?;

        let amount = PricingEngine::calculate_first_payment(tier, add_on_ids);
        let includes_setup = tier.has_setup_fee();
        let setup_fee = tier.setup_fee_usdt();

        let payment = UsdtPayment::new(
            subscription.id,
            tenant_id,
            amount,
            self.default_payment_method,
            self.company_wallet.clone(),
            includes_setup,
            setup_fee,
            now_ms,
        );

        self.payments.insert(payment.id, payment.clone());
        Ok(payment)
    }

    /// Submits a USDT TRC20 transaction hash for a payment.
    pub fn submit_payment_tx(
        &mut self,
        payment_id: PaymentId,
        tx_hash: String,
        source_wallet: String,
        block_number: u64,
    ) -> Result<(), SubscriptionError> {
        let payment = self.payments.get_mut(&payment_id).ok_or_else(|| {
            SubscriptionError::PaymentNotFound(payment_id)
        })?;

        payment.submit_tx_hash(tx_hash, source_wallet, block_number)
    }

    /// Confirms a USDT TRC20 payment (admin action for manual, or auto for semi-manual).
    ///
    /// Uses the PaymentSaga to ensure atomic payment processing:
    /// verify_payment → apply_subscription → grant_access → update_audit
    pub fn confirm_payment(
        &mut self,
        payment_id: PaymentId,
        verified_by: String,
        notes: Option<String>,
        now_ms: u64,
    ) -> Result<Subscription, SubscriptionError> {
        let payment = self.payments.get_mut(&payment_id).ok_or_else(|| {
            SubscriptionError::PaymentNotFound(payment_id)
        })?;

        payment.confirm(verified_by.clone(), notes, now_ms)?;

        let tenant_id = payment.tenant_id;
        let amount = payment.amount_usdt;
        let tx_hash = payment.tx_hash.clone().unwrap_or_default();
        let wallet = payment.source_wallet.clone().unwrap_or_default();

        // Execute the payment saga.
        let subscription = self.subscriptions.get(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        let target_tier = if subscription.status == SubscriptionStatus::Trial {
            // First payment: use the tier from the payment context.
            // Default to Business if trial.
            Some(SubscriptionTierName::Business)
        } else {
            None
        };

        let mut ctx = SagaContext::new(tenant_id, subscription.tier);
        ctx.target_tier = target_tier;
        ctx.amount_usdt = Some(amount);
        ctx.tx_hash = Some(tx_hash);
        ctx.wallet_address = Some(wallet);
        ctx.verified_by = Some(verified_by);

        let saga = PaymentSaga;
        saga.execute(&mut ctx)?;

        // Update subscription state.
        let subscription = self.subscriptions.get_mut(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        if let Some(new_tier) = target_tier {
            subscription.tier = new_tier;
        }
        subscription.transition_to(SubscriptionStatus::Active)?;
        subscription.payment_wallet_address = ctx.wallet_address.clone();
        if subscription.tier.has_setup_fee() {
            subscription.setup_fee_paid = true;
        }

        // Convert the trial.
        if subscription.trial_id.is_some() {
            self.trial_manager.convert_trial(&tenant_id, now_ms)?;
        }

        // Update usage limits for the new tier.
        self.usage_meter.update_limits_for_tier(tenant_id, subscription.tier, now_ms);

        Ok(subscription.clone())
    }

    // -----------------------------------------------------------------------
    // Cancellation
    // -----------------------------------------------------------------------

    /// Cancels a subscription.
    ///
    /// Uses the CancellationSaga to ensure atomic cancellation:
    /// revoke_access → cancel_subscription → process_refund → notify_user
    pub fn cancel_subscription(
        &mut self,
        tenant_id: TenantId,
        now_ms: u64,
    ) -> Result<Subscription, SubscriptionError> {
        let subscription = self.subscriptions.get(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        let mut ctx = SagaContext::new(tenant_id, subscription.tier);
        ctx.subscription_status = subscription.status;
        ctx.amount_usdt = Some(subscription.tier.monthly_price_usdt());

        let saga = CancellationSaga;
        saga.execute(&mut ctx)?;

        // Update subscription state.
        let subscription = self.subscriptions.get_mut(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        subscription.transition_to(SubscriptionStatus::Cancelled)?;
        subscription.cancelled_at_ms = Some(now_ms);

        Ok(subscription.clone())
    }

    // -----------------------------------------------------------------------
    // Renewal
    // -----------------------------------------------------------------------

    /// Renews a subscription.
    ///
    /// Uses the RenewalSaga to ensure atomic renewal:
    /// verify_renewal → extend_subscription → update_audit → notify_user
    pub fn renew_subscription(
        &mut self,
        tenant_id: TenantId,
        tx_hash: String,
        now_ms: u64,
    ) -> Result<Subscription, SubscriptionError> {
        let subscription = self.subscriptions.get(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        let mut ctx = SagaContext::new(tenant_id, subscription.tier);
        ctx.subscription_status = subscription.status;
        ctx.amount_usdt = Some(subscription.tier.monthly_price_usdt());
        ctx.tx_hash = Some(tx_hash);

        let saga = RenewalSaga;
        saga.execute(&mut ctx)?;

        // Update subscription state.
        let subscription = self.subscriptions.get_mut(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        if subscription.status == SubscriptionStatus::PastDue {
            subscription.transition_to(SubscriptionStatus::Active)?;
        }

        // Extend the billing period by 30 days.
        subscription.current_period_start_ms = now_ms;
        subscription.current_period_end_ms = now_ms + (30 * 24 * 60 * 60 * 1000);

        // Reset daily usage counters.
        self.usage_meter.reset_daily_counters(tenant_id, now_ms);

        Ok(subscription.clone())
    }

    // -----------------------------------------------------------------------
    // Upgrade
    // -----------------------------------------------------------------------

    /// Upgrades a subscription to a higher tier.
    ///
    /// Uses the UpgradeSaga to ensure atomic upgrade:
    /// validate_upgrade → calculate_proration → verify_payment →
    /// apply_new_tier → update_access → update_audit
    pub fn upgrade_subscription(
        &mut self,
        tenant_id: TenantId,
        target_tier: SubscriptionTierName,
        tx_hash: String,
        days_remaining: u32,
        days_in_period: u32,
        now_ms: u64,
    ) -> Result<Subscription, SubscriptionError> {
        let subscription = self.subscriptions.get(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        let mut ctx = SagaContext::new(tenant_id, subscription.tier);
        ctx.subscription_status = subscription.status;
        ctx.target_tier = Some(target_tier);
        ctx.tx_hash = Some(tx_hash);
        ctx.days_remaining = Some(days_remaining);
        ctx.days_in_period = Some(days_in_period);

        let saga = UpgradeSaga;
        saga.execute(&mut ctx)?;

        // Update subscription state.
        let subscription = self.subscriptions.get_mut(&tenant_id).ok_or_else(|| {
            SubscriptionError::SubscriptionNotFound(zenic_proto::SubscriptionId::new())
        })?;

        subscription.tier = target_tier;

        // Update usage limits for the new tier.
        self.usage_meter.update_limits_for_tier(tenant_id, target_tier, now_ms);

        Ok(subscription.clone())
    }

    // -----------------------------------------------------------------------
    // Feature Gates
    // -----------------------------------------------------------------------

    /// Checks if a feature is available for a tenant.
    pub fn check_feature(&self, tenant_id: TenantId, feature: &str) -> bool {
        if let Some(subscription) = self.subscriptions.get(&tenant_id) {
            FeatureGate::check_feature(feature, subscription.tier, &subscription.add_ons)
        } else {
            false
        }
    }

    // -----------------------------------------------------------------------
    // Usage Metering
    // -----------------------------------------------------------------------

    /// Records usage for a tenant.
    pub fn record_usage(
        &mut self,
        tenant_id: TenantId,
        usage_type: UsageType,
        amount: u64,
        now_ms: u64,
    ) -> Result<(), SubscriptionError> {
        self.usage_meter.increment_usage(tenant_id, usage_type, amount, now_ms)
    }

    /// Checks if a tenant can perform an action without exceeding limits.
    pub fn check_usage_limit(
        &self,
        tenant_id: TenantId,
        usage_type: UsageType,
        amount: u64,
    ) -> Result<(), SubscriptionError> {
        self.usage_meter.check_limit(tenant_id, usage_type, amount)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
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
