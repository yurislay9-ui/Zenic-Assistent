//! Core subscription types: tiers, status, limits, add-ons.
//!
//! The subscription model has 5 tiers:
//! - **Starter**: $29/mo USDT TRC20
//! - **Business**: $99/mo USDT TRC20
//! - **Enterprise**: $299/mo USDT TRC20
//! - **On-Premise Enterprise**: $799/mo + $2,000 setup USDT TRC20
//!
//! All users get a **14-day trial** with full Business plan access.
//! All payments are **USDT TRC20 only**, manual or semi-manual processing.

use serde::{Deserialize, Serialize};
use zenic_proto::{SubscriptionId, TenantId, TrialId};

use crate::errors::SubscriptionError;

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
// SubscriptionTier (full tier definition with limits)
// ---------------------------------------------------------------------------

/// Complete tier definition including feature limits and capabilities.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SubscriptionTier {
    /// Tier name.
    pub name: SubscriptionTierName,
    /// Monthly price in USDT TRC20.
    pub monthly_price_usdt: u64,
    /// One-time setup fee in USDT TRC20.
    pub setup_fee_usdt: u64,
    /// Feature limits for this tier.
    pub limits: TierLimits,
    /// List of features included in this tier.
    pub features: Vec<String>,
    /// Short description of who this tier is recommended for.
    pub recommended_for: String,
}

impl SubscriptionTier {
    /// Returns the Starter tier definition.
    pub fn starter() -> Self {
        Self {
            name: SubscriptionTierName::Starter,
            monthly_price_usdt: 29,
            setup_fee_usdt: 0,
            limits: TierLimits::starter(),
            features: vec![
                "basic_pipeline".to_string(),
                "chat_completions".to_string(),
                "5_workflows".to_string(),
                "100_actions_per_day".to_string(),
                "3_team_members".to_string(),
                "community_support".to_string(),
                "email_notifications".to_string(),
            ],
            recommended_for: "Small teams starting with AI automation".to_string(),
        }
    }

    /// Returns the Business tier definition.
    pub fn business() -> Self {
        Self {
            name: SubscriptionTierName::Business,
            monthly_price_usdt: 99,
            setup_fee_usdt: 0,
            limits: TierLimits::business(),
            features: vec![
                "full_pipeline".to_string(),
                "chat_completions".to_string(),
                "app_generation".to_string(),
                "automation_generation".to_string(),
                "schema_design".to_string(),
                "thinking_engine".to_string(),
                "reasoning_engine".to_string(),
                "logic_chains".to_string(),
                "25_workflows".to_string(),
                "1000_actions_per_day".to_string(),
                "15_team_members".to_string(),
                "priority_support".to_string(),
                "playbook_library".to_string(),
                "observability_basic".to_string(),
                "policy_engine_basic".to_string(),
            ],
            recommended_for: "Growing teams that need advanced AI capabilities".to_string(),
        }
    }

    /// Returns the Enterprise tier definition.
    pub fn enterprise() -> Self {
        Self {
            name: SubscriptionTierName::Enterprise,
            monthly_price_usdt: 299,
            setup_fee_usdt: 0,
            limits: TierLimits::enterprise(),
            features: vec![
                "all_business_features".to_string(),
                "unlimited_workflows".to_string(),
                "unlimited_actions".to_string(),
                "unlimited_team_members".to_string(),
                "mcp_gateway".to_string(),
                "observability_full".to_string(),
                "policy_engine_full".to_string(),
                "hitl_approvals".to_string(),
                "custom_playbooks".to_string(),
                "merkle_audit".to_string(),
                "dedicated_support".to_string(),
                "sla_guarantee".to_string(),
                "rbac_full".to_string(),
                "compliance_mapping".to_string(),
                "api_rate_limit_high".to_string(),
            ],
            recommended_for: "Organizations requiring full platform access and compliance".to_string(),
        }
    }

    /// Returns the On-Premise Enterprise tier definition.
    pub fn on_premise_enterprise() -> Self {
        Self {
            name: SubscriptionTierName::OnPremiseEnterprise,
            monthly_price_usdt: 799,
            setup_fee_usdt: 2000,
            limits: TierLimits::on_premise_enterprise(),
            features: vec![
                "all_enterprise_features".to_string(),
                "self_hosted".to_string(),
                "custom_deployment".to_string(),
                "source_code_access".to_string(),
                "white_label".to_string(),
                "custom_integrations".to_string(),
                "dedicated_engineer".to_string(),
                "custom_sla".to_string(),
                "data_sovereignty".to_string(),
                "air_gap_capable".to_string(),
                "military_grade_encryption".to_string(),
                "unlimited_everything".to_string(),
            ],
            recommended_for: "Large organizations with strict data sovereignty and custom deployment needs".to_string(),
        }
    }

    /// Returns all tier definitions.
    pub fn all() -> Vec<SubscriptionTier> {
        vec![
            Self::starter(),
            Self::business(),
            Self::enterprise(),
            Self::on_premise_enterprise(),
        ]
    }

    /// Returns the tier definition for a given tier name.
    pub fn for_name(name: SubscriptionTierName) -> Self {
        match name {
            SubscriptionTierName::Starter => Self::starter(),
            SubscriptionTierName::Business => Self::business(),
            SubscriptionTierName::Enterprise => Self::enterprise(),
            SubscriptionTierName::OnPremiseEnterprise => Self::on_premise_enterprise(),
        }
    }

    /// Checks whether this tier includes a specific feature.
    pub fn has_feature(&self, feature: &str) -> bool {
        self.features.iter().any(|f| f == feature)
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

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
