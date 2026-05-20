//! Subscription types — Subscription status, add-ons, and Subscription struct.

use serde::{Deserialize, Serialize};
use zenic_proto::{SubscriptionId, TenantId, TrialId};

use crate::errors::SubscriptionError;

use super::tier::{SubscriptionTier, SubscriptionTierName, TierLimits};

// ---------------------------------------------------------------------------
// SubscriptionStatus
// ---------------------------------------------------------------------------

/// Status of a subscription.
///
/// Lifecycle:
/// `Trial → Active → PastDue → Cancelled`
///                  ↘ Expired
/// `Active → Suspended → Active`
/// `Active → Downgraded → Active`
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SubscriptionStatus {
    /// 14-day trial period (Business plan access).
    Trial,
    /// Active paid subscription.
    Active,
    /// Payment overdue, grace period active.
    PastDue,
    /// Subscription suspended due to payment failure.
    Suspended,
    /// Subscription cancelled by user.
    Cancelled,
    /// Subscription expired (end of billing cycle after cancellation).
    Expired,
    /// Subscription downgraded (awaiting payment for new tier).
    Downgraded,
}

impl SubscriptionStatus {
    /// Whether the subscription is in an active (usable) state.
    pub fn is_active(&self) -> bool {
        matches!(self, Self::Trial | Self::Active)
    }

    /// Whether the subscription is in a terminal state.
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Cancelled | Self::Expired)
    }

    /// Validates that a transition from `self` to `next` is legal.
    pub fn can_transition_to(&self, next: SubscriptionStatus) -> bool {
        match (self, next) {
            (Self::Trial, Self::Active) => true,
            (Self::Trial, Self::Cancelled) => true,
            (Self::Trial, Self::Expired) => true,
            (Self::Active, Self::PastDue) => true,
            (Self::Active, Self::Suspended) => true,
            (Self::Active, Self::Cancelled) => true,
            (Self::Active, Self::Downgraded) => true,
            (Self::PastDue, Self::Active) => true,
            (Self::PastDue, Self::Suspended) => true,
            (Self::PastDue, Self::Cancelled) => true,
            (Self::Suspended, Self::Active) => true,
            (Self::Suspended, Self::Cancelled) => true,
            (Self::Downgraded, Self::Active) => true,
            (Self::Downgraded, Self::Cancelled) => true,
            _ => false,
        }
    }
}

impl std::fmt::Display for SubscriptionStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Trial => write!(f, "trial"),
            Self::Active => write!(f, "active"),
            Self::PastDue => write!(f, "past_due"),
            Self::Suspended => write!(f, "suspended"),
            Self::Cancelled => write!(f, "cancelled"),
            Self::Expired => write!(f, "expired"),
            Self::Downgraded => write!(f, "downgraded"),
        }
    }
}

// ---------------------------------------------------------------------------
// AddOn
// ---------------------------------------------------------------------------

/// Unique identifier for an add-on.
pub type AddOnId = String;

/// Add-on that can be purchased on top of a subscription tier.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AddOn {
    /// Unique add-on identifier.
    pub id: AddOnId,
    /// Human-readable name.
    pub name: String,
    /// Monthly price in USDT TRC20.
    pub monthly_price_usdt: u64,
    /// Description of what this add-on provides.
    pub description: String,
    /// Which tiers this add-on is compatible with (empty = all).
    pub compatible_tiers: Vec<SubscriptionTierName>,
}

impl AddOn {
    /// Extra workflow slots add-on.
    pub fn extra_workflows() -> Self {
        Self {
            id: "extra_workflows_10".to_string(),
            name: "Extra Workflows (+10)".to_string(),
            monthly_price_usdt: 10,
            description: "Add 10 additional workflow slots".to_string(),
            compatible_tiers: vec![SubscriptionTierName::Starter, SubscriptionTierName::Business],
        }
    }

    /// Extra team members add-on.
    pub fn extra_team_members() -> Self {
        Self {
            id: "extra_team_members_5".to_string(),
            name: "Extra Team Members (+5)".to_string(),
            monthly_price_usdt: 15,
            description: "Add 5 additional team member seats".to_string(),
            compatible_tiers: vec![SubscriptionTierName::Starter, SubscriptionTierName::Business],
        }
    }

    /// Advanced analytics add-on.
    pub fn advanced_analytics() -> Self {
        Self {
            id: "advanced_analytics".to_string(),
            name: "Advanced Analytics".to_string(),
            monthly_price_usdt: 25,
            description: "Full observability dashboard and analytics".to_string(),
            compatible_tiers: vec![SubscriptionTierName::Starter, SubscriptionTierName::Business],
        }
    }

    /// Policy engine add-on.
    pub fn policy_engine() -> Self {
        Self {
            id: "policy_engine".to_string(),
            name: "Policy Engine".to_string(),
            monthly_price_usdt: 30,
            description: "Compliance mapping and policy enforcement".to_string(),
            compatible_tiers: vec![SubscriptionTierName::Business],
        }
    }

    /// HITL approvals add-on.
    pub fn hitl_approvals() -> Self {
        Self {
            id: "hitl_approvals".to_string(),
            name: "HITL Approvals".to_string(),
            monthly_price_usdt: 35,
            description: "Human-in-the-loop approval chains".to_string(),
            compatible_tiers: vec![SubscriptionTierName::Business],
        }
    }

    /// Returns all available add-ons.
    pub fn all() -> Vec<AddOn> {
        vec![
            Self::extra_workflows(),
            Self::extra_team_members(),
            Self::advanced_analytics(),
            Self::policy_engine(),
            Self::hitl_approvals(),
        ]
    }

    /// Checks if this add-on is compatible with a given tier.
    pub fn is_compatible_with(&self, tier: SubscriptionTierName) -> bool {
        if self.compatible_tiers.is_empty() {
            return true;
        }
        self.compatible_tiers.contains(&tier)
    }
}

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
