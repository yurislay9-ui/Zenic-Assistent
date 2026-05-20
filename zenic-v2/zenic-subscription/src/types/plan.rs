//! Plan definitions: subscription tiers and add-ons.

use serde::{Deserialize, Serialize};

use super::core::{SubscriptionTierName, TierLimits};

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
