//! Subscription types — Tier definitions and limits.

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
