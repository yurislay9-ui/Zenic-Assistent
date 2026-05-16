//! Usage metering: track and enforce usage limits per subscription tier.

use serde::{Deserialize, Serialize};
use zenic_proto::TenantId;

use crate::errors::SubscriptionError;
use crate::types::{SubscriptionTierName, TierLimits};

// ---------------------------------------------------------------------------
// UsageType
// ---------------------------------------------------------------------------

/// Types of usage that can be metered.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum UsageType {
    /// Number of workflows created.
    Workflows,
    /// Number of actions executed per day.
    ActionsDaily,
    /// Number of team members.
    TeamMembers,
    /// Number of API calls per minute.
    ApiCallsPerMinute,
    /// Storage usage in MB.
    StorageMb,
    /// Number of concurrent sessions.
    ConcurrentSessions,
    /// Number of playbooks.
    Playbooks,
    /// Number of policy rules.
    PolicyRules,
    /// HITL approval chain depth.
    ApprovalChainDepth,
}

impl UsageType {
    /// Returns the limit key name.
    pub fn limit_key(&self) -> &'static str {
        match self {
            Self::Workflows => "max_workflows",
            Self::ActionsDaily => "max_actions_per_day",
            Self::TeamMembers => "max_team_members",
            Self::ApiCallsPerMinute => "max_api_calls_per_minute",
            Self::StorageMb => "max_storage_mb",
            Self::ConcurrentSessions => "max_concurrent_sessions",
            Self::Playbooks => "max_playbooks",
            Self::PolicyRules => "max_policy_rules",
            Self::ApprovalChainDepth => "max_approval_chain_depth",
        }
    }
}

impl std::fmt::Display for UsageType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.limit_key())
    }
}

// ---------------------------------------------------------------------------
// UsageRecord
// ---------------------------------------------------------------------------

/// A usage record for a tenant.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UsageRecord {
    /// The tenant this usage belongs to.
    pub tenant_id: TenantId,
    /// Type of usage.
    pub usage_type: UsageType,
    /// Current usage value.
    pub current_value: u64,
    /// Maximum allowed value for the current tier.
    pub limit_value: u64,
    /// When this record was last updated (ms since epoch).
    pub updated_at_ms: u64,
}

impl UsageRecord {
    /// Creates a new usage record.
    pub fn new(
        tenant_id: TenantId,
        usage_type: UsageType,
        current_value: u64,
        limit_value: u64,
        updated_at_ms: u64,
    ) -> Self {
        Self {
            tenant_id,
            usage_type,
            current_value,
            limit_value,
            updated_at_ms,
        }
    }

    /// Whether the usage is within the limit.
    pub fn is_within_limit(&self) -> bool {
        self.current_value <= self.limit_value
    }

    /// Usage as a percentage of the limit (0-100+).
    pub fn usage_percent(&self) -> f64 {
        if self.limit_value == 0 {
            return 0.0;
        }
        (self.current_value as f64 / self.limit_value as f64) * 100.0
    }

    /// Whether the usage is at or above the warning threshold (80%).
    pub fn is_near_limit(&self) -> bool {
        self.usage_percent() >= 80.0
    }
}

// ---------------------------------------------------------------------------
// UsageMeter
// ---------------------------------------------------------------------------

/// Tracks and enforces usage limits per tenant.
pub struct UsageMeter {
    /// Usage records indexed by (tenant_id, usage_type).
    records: std::collections::HashMap<(TenantId, UsageType), UsageRecord>,
}

impl UsageMeter {
    /// Creates a new usage meter.
    pub fn new() -> Self {
        Self {
            records: std::collections::HashMap::new(),
        }
    }

    /// Initializes usage records for a tenant based on their tier limits.
    pub fn initialize_for_tenant(
        &mut self,
        tenant_id: TenantId,
        tier: SubscriptionTierName,
        now_ms: u64,
    ) {
        let limits = TierLimits::for_name(tier);

        let entries = vec![
            (UsageType::Workflows, 0, limits.max_workflows as u64),
            (UsageType::ActionsDaily, 0, limits.max_actions_per_day as u64),
            (UsageType::TeamMembers, 0, limits.max_team_members as u64),
            (UsageType::ApiCallsPerMinute, 0, limits.max_api_calls_per_minute as u64),
            (UsageType::StorageMb, 0, limits.max_storage_mb as u64),
            (UsageType::ConcurrentSessions, 0, limits.max_concurrent_sessions as u64),
            (UsageType::Playbooks, 0, limits.max_playbooks as u64),
            (UsageType::PolicyRules, 0, limits.max_policy_rules as u64),
            (UsageType::ApprovalChainDepth, 0, limits.max_approval_chain_depth as u64),
        ];

        for (usage_type, initial, limit) in entries {
            self.records.insert(
                (tenant_id, usage_type),
                UsageRecord::new(tenant_id, usage_type, initial, limit, now_ms),
            );
        }
    }

    /// Records usage increment for a tenant.
    pub fn increment_usage(
        &mut self,
        tenant_id: TenantId,
        usage_type: UsageType,
        amount: u64,
        now_ms: u64,
    ) -> Result<(), SubscriptionError> {
        let key = (tenant_id, usage_type);

        if let Some(record) = self.records.get_mut(&key) {
            let new_value = record.current_value + amount;
            if new_value > record.limit_value {
                return Err(SubscriptionError::UsageLimitExceeded {
                    usage_type: usage_type.to_string(),
                    limit: record.limit_value,
                    current: new_value,
                });
            }
            record.current_value = new_value;
            record.updated_at_ms = now_ms;
        }

        Ok(())
    }

    /// Checks if a tenant can perform an action without exceeding limits.
    pub fn check_limit(
        &self,
        tenant_id: TenantId,
        usage_type: UsageType,
        amount: u64,
    ) -> Result<(), SubscriptionError> {
        let key = (tenant_id, usage_type);

        if let Some(record) = self.records.get(&key) {
            if record.current_value + amount > record.limit_value {
                return Err(SubscriptionError::UsageLimitExceeded {
                    usage_type: usage_type.to_string(),
                    limit: record.limit_value,
                    current: record.current_value + amount,
                });
            }
        }

        Ok(())
    }

    /// Gets the current usage for a tenant and usage type.
    pub fn get_usage(&self, tenant_id: TenantId, usage_type: UsageType) -> Option<&UsageRecord> {
        self.records.get(&(tenant_id, usage_type))
    }

    /// Updates the limits when a tenant changes tiers.
    pub fn update_limits_for_tier(
        &mut self,
        tenant_id: TenantId,
        tier: SubscriptionTierName,
        now_ms: u64,
    ) {
        let limits = TierLimits::for_name(tier);

        let limit_updates = vec![
            (UsageType::Workflows, limits.max_workflows as u64),
            (UsageType::ActionsDaily, limits.max_actions_per_day as u64),
            (UsageType::TeamMembers, limits.max_team_members as u64),
            (UsageType::ApiCallsPerMinute, limits.max_api_calls_per_minute as u64),
            (UsageType::StorageMb, limits.max_storage_mb as u64),
            (UsageType::ConcurrentSessions, limits.max_concurrent_sessions as u64),
            (UsageType::Playbooks, limits.max_playbooks as u64),
            (UsageType::PolicyRules, limits.max_policy_rules as u64),
            (UsageType::ApprovalChainDepth, limits.max_approval_chain_depth as u64),
        ];

        for (usage_type, new_limit) in limit_updates {
            let key = (tenant_id, usage_type);
            if let Some(record) = self.records.get_mut(&key) {
                record.limit_value = new_limit;
                record.updated_at_ms = now_ms;
            }
        }
    }

    /// Resets daily counters (e.g., actions per day).
    pub fn reset_daily_counters(&mut self, tenant_id: TenantId, now_ms: u64) {
        for (key, record) in &mut self.records {
            if key.0 == tenant_id && key.1 == UsageType::ActionsDaily {
                record.current_value = 0;
                record.updated_at_ms = now_ms;
            }
        }
    }

    /// Returns all usage records that are near or at their limits.
    pub fn get_near_limit_records(&self) -> Vec<&UsageRecord> {
        self.records.values().filter(|r| r.is_near_limit()).collect()
    }

    /// Returns the number of tracked records.
    pub fn record_count(&self) -> usize {
        self.records.len()
    }
}

impl Default for UsageMeter {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn usage_record_within_limit() {
        let record = UsageRecord::new(TenantId::new(), UsageType::Workflows, 3, 5, 1000);
        assert!(record.is_within_limit());
        assert!(!record.is_near_limit());
    }

    #[test]
    fn usage_record_near_limit() {
        let record = UsageRecord::new(TenantId::new(), UsageType::Workflows, 4, 5, 1000);
        assert!(record.is_near_limit());
    }

    #[test]
    fn usage_record_over_limit() {
        let record = UsageRecord::new(TenantId::new(), UsageType::Workflows, 6, 5, 1000);
        assert!(!record.is_within_limit());
    }

    #[test]
    fn usage_meter_initialize() {
        let mut meter = UsageMeter::new();
        let tenant = TenantId::new();
        meter.initialize_for_tenant(tenant, SubscriptionTierName::Starter, 1000);

        let record = meter.get_usage(tenant, UsageType::Workflows).expect("record");
        assert_eq!(record.current_value, 0);
        assert_eq!(record.limit_value, 5); // Starter: 5 workflows
    }

    #[test]
    fn usage_meter_increment() {
        let mut meter = UsageMeter::new();
        let tenant = TenantId::new();
        meter.initialize_for_tenant(tenant, SubscriptionTierName::Starter, 1000);

        meter.increment_usage(tenant, UsageType::Workflows, 3, 2000).expect("increment");

        let record = meter.get_usage(tenant, UsageType::Workflows).expect("record");
        assert_eq!(record.current_value, 3);
    }

    #[test]
    fn usage_meter_exceed_limit() {
        let mut meter = UsageMeter::new();
        let tenant = TenantId::new();
        meter.initialize_for_tenant(tenant, SubscriptionTierName::Starter, 1000);

        // Starter has 5 workflow limit.
        meter.increment_usage(tenant, UsageType::Workflows, 5, 2000).expect("increment");

        let result = meter.increment_usage(tenant, UsageType::Workflows, 1, 3000);
        assert!(result.is_err());
    }

    #[test]
    fn usage_meter_check_limit() {
        let mut meter = UsageMeter::new();
        let tenant = TenantId::new();
        meter.initialize_for_tenant(tenant, SubscriptionTierName::Starter, 1000);

        assert!(meter.check_limit(tenant, UsageType::Workflows, 5).is_ok());
        assert!(meter.check_limit(tenant, UsageType::Workflows, 6).is_err());
    }

    #[test]
    fn usage_meter_update_limits() {
        let mut meter = UsageMeter::new();
        let tenant = TenantId::new();
        meter.initialize_for_tenant(tenant, SubscriptionTierName::Starter, 1000);

        meter.update_limits_for_tier(tenant, SubscriptionTierName::Business, 2000);

        let record = meter.get_usage(tenant, UsageType::Workflows).expect("record");
        assert_eq!(record.limit_value, 25); // Business: 25 workflows
    }

    #[test]
    fn usage_meter_reset_daily() {
        let mut meter = UsageMeter::new();
        let tenant = TenantId::new();
        meter.initialize_for_tenant(tenant, SubscriptionTierName::Starter, 1000);

        meter.increment_usage(tenant, UsageType::ActionsDaily, 50, 2000).expect("increment");
        meter.reset_daily_counters(tenant, 3000);

        let record = meter.get_usage(tenant, UsageType::ActionsDaily).expect("record");
        assert_eq!(record.current_value, 0);
    }
}
