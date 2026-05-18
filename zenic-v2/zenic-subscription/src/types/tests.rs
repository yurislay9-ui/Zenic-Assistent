//! Subscription types — Unit Tests

use zenic_proto::{TenantId, TrialId};

use super::tier::{SubscriptionTier, SubscriptionTierName, TierLimits};
use super::subscription::{AddOn, Subscription, SubscriptionStatus};

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
