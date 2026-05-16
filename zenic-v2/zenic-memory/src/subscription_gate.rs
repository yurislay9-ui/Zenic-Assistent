//! Subscription Gate — Feature gates by subscription tier [T1]
//!
//! Enforces per-tier quotas on mappings, cache, mechanisms, and ontology.
//!
//! Starter:     Schema Drift only, 10 mappings/mes, LRU 100
//! Business:    Schema Drift + Intent Routing, 50 mappings/mes, LRU 500
//! Enterprise:  All 3 + Ontología, unlimited, LRU 2000
//! On-Premise:  All + Export/Import + Custom, unlimited

use crate::errors::MemoryError;
use crate::types::{FeatureGate, LearningMechanism, SubscriptionTier};

// ---------------------------------------------------------------------------
// SubscriptionGate
// ---------------------------------------------------------------------------

/// Subscription gate that controls access to memory chip features.
///
/// Ensures that operations are only permitted for tenants with
/// the appropriate subscription level.
pub struct SubscriptionGate {
    /// The feature gate configuration for the current tier.
    gate: FeatureGate,
}

impl SubscriptionGate {
    /// Creates a new subscription gate for the given tier.
    pub fn new(tier: SubscriptionTier) -> Self {
        Self {
            gate: FeatureGate::for_tier(tier),
        }
    }

    /// Creates a subscription gate for the Starter tier.
    pub fn starter() -> Self {
        Self::new(SubscriptionTier::Starter)
    }

    /// Creates a subscription gate for the Business tier.
    pub fn business() -> Self {
        Self::new(SubscriptionTier::Business)
    }

    /// Creates a subscription gate for the Enterprise tier.
    pub fn enterprise() -> Self {
        Self::new(SubscriptionTier::Enterprise)
    }

    /// Creates a subscription gate for the On-Premise tier.
    pub fn on_premise() -> Self {
        Self::new(SubscriptionTier::OnPremise)
    }

    /// Checks if a learning mechanism is allowed for this tier.
    pub fn check_mechanism(&self, mechanism: LearningMechanism) -> Result<(), MemoryError> {
        if self.gate.is_mechanism_allowed(mechanism) {
            Ok(())
        } else {
            Err(MemoryError::TierRestricted {
                tier: self.gate.tier.to_string(),
                mechanism: mechanism.to_string(),
            })
        }
    }

    /// Checks if the mapping quota has been exceeded.
    pub fn check_mapping_quota(&self, current_count: u32) -> Result<(), MemoryError> {
        if self.gate.is_mapping_quota_exceeded(current_count) {
            Err(MemoryError::FeatureGateBlocked(format!(
                "Mapping quota exceeded: {} / {} for tier {}",
                current_count, self.gate.max_mappings_per_month, self.gate.tier
            )))
        } else {
            Ok(())
        }
    }

    /// Checks if ontology access is allowed.
    pub fn check_ontology_access(&self) -> Result<(), MemoryError> {
        if self.gate.ontology_access {
            Ok(())
        } else {
            Err(MemoryError::FeatureGateBlocked(format!(
                "Ontology access not available for tier {}", self.gate.tier
            )))
        }
    }

    /// Checks if export/import is allowed.
    pub fn check_export_import(&self) -> Result<(), MemoryError> {
        if self.gate.export_import {
            Ok(())
        } else {
            Err(MemoryError::FeatureGateBlocked(format!(
                "Export/Import not available for tier {}", self.gate.tier
            )))
        }
    }

    /// Returns the maximum cache size for this tier.
    pub fn max_cache_size(&self) -> usize {
        self.gate.lru_cache_size
    }

    /// Returns the feature gate configuration.
    pub fn gate(&self) -> &FeatureGate {
        &self.gate
    }

    /// Returns the subscription tier.
    pub fn tier(&self) -> SubscriptionTier {
        self.gate.tier
    }
}
