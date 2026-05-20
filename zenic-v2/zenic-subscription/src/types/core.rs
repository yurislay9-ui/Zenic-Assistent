//! Core subscription types: tier names, status, and limits.

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// SubscriptionTierName
// ---------------------------------------------------------------------------

/// The 5 subscription tier names for Zenic-Agents.
///
/// Prices are in **USDT TRC20** only.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SubscriptionTierName {
    /// Starter: $29/mo — basic pipeline, limited features.
    Starter,
    /// Business: $99/mo — full pipeline, advanced features, 14-day trial tier.
    Business,
    /// Enterprise: $299/mo — unlimited features, priority support.
    Enterprise,
    /// On-Premise Enterprise: $799/mo + $2,000 setup — self-hosted, custom SLA.
    OnPremiseEnterprise,
}

impl SubscriptionTierName {
    /// Returns all tier names in ascending order.
    pub fn all() -> &'static [SubscriptionTierName] {
        &[
            Self::Starter,
            Self::Business,
            Self::Enterprise,
            Self::OnPremiseEnterprise,
        ]
    }

    /// Monthly price in USDT TRC20.
    pub fn monthly_price_usdt(&self) -> u64 {
        match self {
            Self::Starter => 29,
            Self::Business => 99,
            Self::Enterprise => 299,
            Self::OnPremiseEnterprise => 799,
        }
    }

    /// One-time setup fee in USDT TRC20 (only On-Premise Enterprise has this).
    pub fn setup_fee_usdt(&self) -> u64 {
        match self {
            Self::OnPremiseEnterprise => 2000,
            _ => 0,
        }
    }

    /// Annual price: 10 months (2 months free).
    pub fn annual_price_usdt(&self) -> u64 {
        self.monthly_price_usdt() * 10
    }

    /// Whether this tier has a setup fee.
    pub fn has_setup_fee(&self) -> bool {
        self.setup_fee_usdt() > 0
    }

    /// Human-readable display name.
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Starter => "Starter",
            Self::Business => "Business",
            Self::Enterprise => "Enterprise",
            Self::OnPremiseEnterprise => "On-Premise Enterprise",
        }
    }

    /// Tier rank (0 = lowest). Used for upgrade/downgrade comparisons.
    pub fn rank(&self) -> u8 {
        match self {
            Self::Starter => 0,
            Self::Business => 1,
            Self::Enterprise => 2,
            Self::OnPremiseEnterprise => 3,
        }
    }

    /// Whether an upgrade from `other` to `self` is valid.
    pub fn is_upgrade_from(&self, other: &SubscriptionTierName) -> bool {
        self.rank() > other.rank()
    }

    /// Whether a downgrade from `other` to `self` is valid.
    pub fn is_downgrade_from(&self, other: &SubscriptionTierName) -> bool {
        self.rank() < other.rank()
    }
}

impl std::fmt::Display for SubscriptionTierName {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.display_name())
    }
}

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
            // Trial can go to Active (payment received), Cancelled, or Expired.
            (Self::Trial, Self::Active) => true,
            (Self::Trial, Self::Cancelled) => true,
            (Self::Trial, Self::Expired) => true,

            // Active can go to PastDue, Suspended, Cancelled, or Downgraded.
            (Self::Active, Self::PastDue) => true,
            (Self::Active, Self::Suspended) => true,
            (Self::Active, Self::Cancelled) => true,
            (Self::Active, Self::Downgraded) => true,

            // PastDue can go to Active (payment received), Suspended, or Cancelled.
            (Self::PastDue, Self::Active) => true,
            (Self::PastDue, Self::Suspended) => true,
            (Self::PastDue, Self::Cancelled) => true,

            // Suspended can go to Active (payment received) or Cancelled.
            (Self::Suspended, Self::Active) => true,
            (Self::Suspended, Self::Cancelled) => true,

            // Downgraded can go to Active (payment for new tier) or Cancelled.
            (Self::Downgraded, Self::Active) => true,
            (Self::Downgraded, Self::Cancelled) => true,

            // Terminal states cannot transition.
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
// TierLimits
// ---------------------------------------------------------------------------

/// Feature limits for a subscription tier.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TierLimits {
    /// Maximum number of workflows.
    pub max_workflows: u32,
    /// Maximum actions per day.
    pub max_actions_per_day: u32,
    /// Maximum team members.
    pub max_team_members: u32,
    /// Maximum API calls per minute.
    pub max_api_calls_per_minute: u32,
    /// Maximum storage in MB.
    pub max_storage_mb: u32,
    /// Maximum concurrent sessions.
    pub max_concurrent_sessions: u32,
    /// Maximum playbooks.
    pub max_playbooks: u32,
    /// Maximum policy rules.
    pub max_policy_rules: u32,
    /// Maximum HITL approval chains depth.
    pub max_approval_chain_depth: u32,
    /// Whether custom playbooks are allowed.
    pub custom_playbooks: bool,
    /// Whether full observability is available.
    pub full_observability: bool,
    /// Whether the policy engine is available.
    pub policy_engine: bool,
    /// Whether HITL approvals are available.
    pub hitl_approvals: bool,
    /// Whether Merkle audit logging is available.
    pub merkle_audit: bool,
    /// Whether self-hosted deployment is available.
    pub self_hosted: bool,
}

impl TierLimits {
    pub fn starter() -> Self {
        Self {
            max_workflows: 5,
            max_actions_per_day: 100,
            max_team_members: 3,
            max_api_calls_per_minute: 30,
            max_storage_mb: 500,
            max_concurrent_sessions: 2,
            max_playbooks: 3,
            max_policy_rules: 10,
            max_approval_chain_depth: 0,
            custom_playbooks: false,
            full_observability: false,
            policy_engine: false,
            hitl_approvals: false,
            merkle_audit: false,
            self_hosted: false,
        }
    }

    pub fn business() -> Self {
        Self {
            max_workflows: 25,
            max_actions_per_day: 1000,
            max_team_members: 15,
            max_api_calls_per_minute: 100,
            max_storage_mb: 5000,
            max_concurrent_sessions: 10,
            max_playbooks: 25,
            max_policy_rules: 50,
            max_approval_chain_depth: 3,
            custom_playbooks: false,
            full_observability: false,
            policy_engine: true,
            hitl_approvals: false,
            merkle_audit: false,
            self_hosted: false,
        }
    }

    pub fn enterprise() -> Self {
        Self {
            max_workflows: u32::MAX,
            max_actions_per_day: u32::MAX,
            max_team_members: u32::MAX,
            max_api_calls_per_minute: 1000,
            max_storage_mb: u32::MAX,
            max_concurrent_sessions: u32::MAX,
            max_playbooks: u32::MAX,
            max_policy_rules: u32::MAX,
            max_approval_chain_depth: 10,
            custom_playbooks: true,
            full_observability: true,
            policy_engine: true,
            hitl_approvals: true,
            merkle_audit: true,
            self_hosted: false,
        }
    }

    pub fn on_premise_enterprise() -> Self {
        Self {
            max_workflows: u32::MAX,
            max_actions_per_day: u32::MAX,
            max_team_members: u32::MAX,
            max_api_calls_per_minute: u32::MAX,
            max_storage_mb: u32::MAX,
            max_concurrent_sessions: u32::MAX,
            max_playbooks: u32::MAX,
            max_policy_rules: u32::MAX,
            max_approval_chain_depth: u32::MAX,
            custom_playbooks: true,
            full_observability: true,
            policy_engine: true,
            hitl_approvals: true,
            merkle_audit: true,
            self_hosted: true,
        }
    }
    /// Returns the tier limits for a given tier name.
    pub fn for_name(name: SubscriptionTierName) -> Self {
        match name {
            SubscriptionTierName::Starter => Self::starter(),
            SubscriptionTierName::Business => Self::business(),
            SubscriptionTierName::Enterprise => Self::enterprise(),
            SubscriptionTierName::OnPremiseEnterprise => Self::on_premise_enterprise(),
        }
    }
}
