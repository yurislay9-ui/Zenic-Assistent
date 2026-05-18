//! Subscription entity and billing types.

use serde::{Deserialize, Serialize};
use zenic_proto::{SubscriptionId, TenantId, TrialId};

use crate::errors::SubscriptionError;

use super::core::{SubscriptionStatus, SubscriptionTierName, TierLimits};
use super::plan::{AddOnId, SubscriptionTier};

// ---------------------------------------------------------------------------
// Subscription
// ---------------------------------------------------------------------------

/// A subscription instance for a tenant.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Subscription {
    /// Unique subscription identifier.
    pub id: SubscriptionId,
    /// The tenant that owns this subscription.
    pub tenant_id: TenantId,
    /// Current subscription tier.
    pub tier: SubscriptionTierName,
    /// Current subscription status.
    pub status: SubscriptionStatus,
    /// Optional trial ID if this subscription started with a trial.
    pub trial_id: Option<TrialId>,
    /// Active add-ons.
    pub add_ons: Vec<AddOnId>,
    /// When the subscription was created (ms since epoch).
    pub created_at_ms: u64,
    /// When the current billing period started (ms since epoch).
    pub current_period_start_ms: u64,
    /// When the current billing period ends (ms since epoch).
    pub current_period_end_ms: u64,
    /// When the subscription was cancelled (if applicable).
    pub cancelled_at_ms: Option<u64>,
    /// USDT TRC20 wallet address for payments.
    pub payment_wallet_address: Option<String>,
    /// Whether the setup fee has been paid (for On-Premise Enterprise).
    pub setup_fee_paid: bool,
}

impl Subscription {
    /// Creates a new subscription in Trial status with Business tier.
    pub fn new_trial(tenant_id: TenantId, trial_id: TrialId, now_ms: u64) -> Self {
        Self {
            id: SubscriptionId::new(),
            tenant_id,
            tier: SubscriptionTierName::Business,
            status: SubscriptionStatus::Trial,
            trial_id: Some(trial_id),
            add_ons: Vec::new(),
            created_at_ms: now_ms,
            current_period_start_ms: now_ms,
            current_period_end_ms: now_ms + (14 * 24 * 60 * 60 * 1000), // 14 days
            cancelled_at_ms: None,
            payment_wallet_address: None,
            setup_fee_paid: false,
        }
    }

    /// Creates a new active subscription after payment.
    pub fn new_active(
        tenant_id: TenantId,
        tier: SubscriptionTierName,
        now_ms: u64,
        wallet_address: String,
    ) -> Self {
        let period_end = now_ms + (30 * 24 * 60 * 60 * 1000); // 30 days
        Self {
            id: SubscriptionId::new(),
            tenant_id,
            tier,
            status: SubscriptionStatus::Active,
            trial_id: None,
            add_ons: Vec::new(),
            created_at_ms: now_ms,
            current_period_start_ms: now_ms,
            current_period_end_ms: period_end,
            cancelled_at_ms: None,
            payment_wallet_address: Some(wallet_address),
            setup_fee_paid: tier.setup_fee_usdt() == 0,
        }
    }

    /// Transitions the subscription to a new status.
    pub fn transition_to(&mut self, new_status: SubscriptionStatus) -> Result<(), SubscriptionError> {
        if !self.status.can_transition_to(new_status) {
            return Err(SubscriptionError::InvalidTransition {
                from: self.status.to_string(),
                to: new_status.to_string(),
            });
        }
        self.status = new_status;
        Ok(())
    }

    /// Whether this subscription currently has access to the platform.
    pub fn has_access(&self) -> bool {
        self.status.is_active()
    }

    /// Calculates the total monthly cost (tier + add-ons) in USDT TRC20.
    pub fn total_monthly_cost_usdt(&self) -> u64 {
        let tier_price = self.tier.monthly_price_usdt();
        let add_on_cost: u64 = self.add_ons.iter().map(|_| 0).sum(); // Add-on prices resolved by engine
        tier_price + add_on_cost
    }

    /// Returns the tier limits for this subscription's current tier.
    pub fn limits(&self) -> TierLimits {
        SubscriptionTier::for_name(self.tier).limits
    }

    /// Adds an add-on to this subscription.
    pub fn add_add_on(&mut self, add_on_id: AddOnId) {
        if !self.add_ons.contains(&add_on_id) {
            self.add_ons.push(add_on_id);
        }
    }

    /// Removes an add-on from this subscription.
    pub fn remove_add_on(&mut self, add_on_id: &str) {
        self.add_ons.retain(|id| id != add_on_id);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::core::{SubscriptionTierName, SubscriptionStatus, TierLimits};
    use super::super::plan::AddOn;

    #[test]
    fn tier_name_prices() {
        assert_eq!(SubscriptionTierName::Starter.monthly_price_usdt(), 29);
        assert_eq!(SubscriptionTierName::Business.monthly_price_usdt(), 99);
        assert_eq!(SubscriptionTierName::Enterprise.monthly_price_usdt(), 299);
        assert_eq!(SubscriptionTierName::OnPremiseEnterprise.monthly_price_usdt(), 799);
    }

    #[test]
    fn tier_name_setup_fee() {
        assert_eq!(SubscriptionTierName::Starter.setup_fee_usdt(), 0);
        assert_eq!(SubscriptionTierName::Business.setup_fee_usdt(), 0);
        assert_eq!(SubscriptionTierName::Enterprise.setup_fee_usdt(), 0);
        assert_eq!(SubscriptionTierName::OnPremiseEnterprise.setup_fee_usdt(), 2000);
    }

    #[test]
    fn tier_name_annual_price() {
        assert_eq!(SubscriptionTierName::Starter.annual_price_usdt(), 290);
        assert_eq!(SubscriptionTierName::Business.annual_price_usdt(), 990);
    }

    #[test]
    fn tier_rank_ordering() {
        assert!(SubscriptionTierName::Business.rank() > SubscriptionTierName::Starter.rank());
        assert!(SubscriptionTierName::Enterprise.rank() > SubscriptionTierName::Business.rank());
        assert!(SubscriptionTierName::OnPremiseEnterprise.rank() > SubscriptionTierName::Enterprise.rank());
    }

    #[test]
    fn is_upgrade_from() {
        assert!(SubscriptionTierName::Business.is_upgrade_from(&SubscriptionTierName::Starter));
        assert!(!SubscriptionTierName::Starter.is_upgrade_from(&SubscriptionTierName::Business));
    }

    #[test]
    fn subscription_status_transitions() {
        assert!(SubscriptionStatus::Trial.can_transition_to(SubscriptionStatus::Active));
        assert!(SubscriptionStatus::Trial.can_transition_to(SubscriptionStatus::Cancelled));
        assert!(SubscriptionStatus::Active.can_transition_to(SubscriptionStatus::PastDue));
        assert!(SubscriptionStatus::PastDue.can_transition_to(SubscriptionStatus::Active));
        assert!(!SubscriptionStatus::Cancelled.can_transition_to(SubscriptionStatus::Active));
    }

    #[test]
    fn subscription_status_active() {
        assert!(SubscriptionStatus::Trial.is_active());
        assert!(SubscriptionStatus::Active.is_active());
        assert!(!SubscriptionStatus::PastDue.is_active());
        assert!(!SubscriptionStatus::Suspended.is_active());
        assert!(!SubscriptionStatus::Cancelled.is_active());
    }

    #[test]
    fn subscription_new_trial() {
        let sub = Subscription::new_trial(TenantId::new(), TrialId::new(), 1000);
        assert_eq!(sub.status, SubscriptionStatus::Trial);
        assert_eq!(sub.tier, SubscriptionTierName::Business);
        assert!(sub.trial_id.is_some());
        assert!(sub.has_access());
    }

    #[test]
    fn subscription_transition() {
        let mut sub = Subscription::new_trial(TenantId::new(), TrialId::new(), 1000);
        sub.transition_to(SubscriptionStatus::Active).expect("transition");
        assert_eq!(sub.status, SubscriptionStatus::Active);
    }

    #[test]
    fn subscription_invalid_transition() {
        let mut sub = Subscription::new_active(
            TenantId::new(),
            SubscriptionTierName::Starter,
            1000,
            "TXYZ...".to_string(),
        );
        let result = sub.transition_to(SubscriptionStatus::Trial);
        assert!(result.is_err());
    }

    #[test]
    fn tier_features() {
        let starter = SubscriptionTier::starter();
        assert!(starter.has_feature("basic_pipeline"));
        assert!(!starter.has_feature("thinking_engine"));

        let business = SubscriptionTier::business();
        assert!(business.has_feature("thinking_engine"));
    }

    #[test]
    fn add_on_compatibility() {
        let add_on = AddOn::policy_engine();
        assert!(add_on.is_compatible_with(SubscriptionTierName::Business));
        assert!(!add_on.is_compatible_with(SubscriptionTierName::Starter));
    }

    #[test]
    fn tier_limits_starter() {
        let limits = TierLimits::starter();
        assert_eq!(limits.max_workflows, 5);
        assert_eq!(limits.max_actions_per_day, 100);
        assert!(!limits.policy_engine);
    }

    #[test]
    fn tier_limits_on_premise() {
        let limits = TierLimits::on_premise_enterprise();
        assert_eq!(limits.max_workflows, u32::MAX);
        assert!(limits.self_hosted);
    }
}
