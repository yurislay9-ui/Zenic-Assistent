//! Trial system: 14-day automatic trial for ALL users with Business plan access.
//!
//! Every new user gets a 14-day trial of the Business plan, automatically.
//! No credit card or payment required. The trial starts immediately upon signup.

use serde::{Deserialize, Serialize};
use zenic_proto::{SubscriptionId, TenantId, TrialId};

use crate::errors::SubscriptionError;

// ---------------------------------------------------------------------------
// TrialStatus
// ---------------------------------------------------------------------------

/// Status of a trial period.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TrialStatus {
    /// Trial is active.
    Active,
    /// Trial has been converted to a paid subscription.
    Converted,
    /// Trial has expired without conversion.
    Expired,
    /// Trial was cancelled by the user.
    Cancelled,
}

impl TrialStatus {
    /// Whether the trial is in an active (usable) state.
    pub fn is_active(&self) -> bool {
        matches!(self, Self::Active)
    }

    /// Whether the trial is in a terminal state.
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Converted | Self::Expired | Self::Cancelled)
    }
}

impl std::fmt::Display for TrialStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Active => write!(f, "active"),
            Self::Converted => write!(f, "converted"),
            Self::Expired => write!(f, "expired"),
            Self::Cancelled => write!(f, "cancelled"),
        }
    }
}

// ---------------------------------------------------------------------------
// Trial
// ---------------------------------------------------------------------------

/// A 14-day trial period for a tenant.
///
/// All users get automatic Business plan access during the trial.
/// No payment method required.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Trial {
    /// Unique trial identifier.
    pub id: TrialId,
    /// The tenant this trial belongs to.
    pub tenant_id: TenantId,
    /// The subscription created during the trial.
    pub subscription_id: Option<SubscriptionId>,
    /// Trial status.
    pub status: TrialStatus,
    /// When the trial started (ms since epoch).
    pub started_at_ms: u64,
    /// When the trial expires (ms since epoch).
    pub expires_at_ms: u64,
    /// When the trial was converted to a paid subscription (if applicable).
    pub converted_at_ms: Option<u64>,
    /// When the trial was cancelled (if applicable).
    pub cancelled_at_ms: Option<u64>,
    /// Number of days remaining in the trial.
    pub days_remaining: u32,
    /// Whether the user was notified about upcoming expiration.
    pub expiration_notified: bool,
}

/// Duration of the trial period in days.
pub const TRIAL_DURATION_DAYS: u32 = 14;

/// Duration of the trial period in milliseconds.
pub const TRIAL_DURATION_MS: u64 = TRIAL_DURATION_DAYS as u64 * 24 * 60 * 60 * 1000;

impl Trial {
    /// Creates a new 14-day trial for a tenant.
    pub fn new(tenant_id: TenantId, now_ms: u64) -> Self {
        Self {
            id: TrialId::new(),
            tenant_id,
            subscription_id: None,
            status: TrialStatus::Active,
            started_at_ms: now_ms,
            expires_at_ms: now_ms + TRIAL_DURATION_MS,
            converted_at_ms: None,
            cancelled_at_ms: None,
            days_remaining: TRIAL_DURATION_DAYS,
            expiration_notified: false,
        }
    }

    /// Whether the trial has expired based on the current time.
    pub fn is_expired_at(&self, now_ms: u64) -> bool {
        now_ms >= self.expires_at_ms
    }

    /// Calculates the number of days remaining in the trial.
    pub fn calculate_days_remaining(&self, now_ms: u64) -> u32 {
        if now_ms >= self.expires_at_ms {
            0
        } else {
            let remaining_ms = self.expires_at_ms - now_ms;
            (remaining_ms / (24 * 60 * 60 * 1000)) as u32
        }
    }

    /// Converts the trial to a paid subscription.
    pub fn convert(&mut self, now_ms: u64) -> Result<(), SubscriptionError> {
        if self.status != TrialStatus::Active {
            return Err(SubscriptionError::InvalidState {
                action: "convert trial".to_string(),
                state: self.status.to_string(),
            });
        }
        self.status = TrialStatus::Converted;
        self.converted_at_ms = Some(now_ms);
        self.days_remaining = 0;
        Ok(())
    }

    /// Cancels the trial.
    pub fn cancel(&mut self, now_ms: u64) -> Result<(), SubscriptionError> {
        if self.status.is_terminal() {
            return Err(SubscriptionError::InvalidState {
                action: "cancel trial".to_string(),
                state: self.status.to_string(),
            });
        }
        self.status = TrialStatus::Cancelled;
        self.cancelled_at_ms = Some(now_ms);
        self.days_remaining = 0;
        Ok(())
    }

    /// Marks the trial as expired.
    pub fn expire(&mut self) -> Result<(), SubscriptionError> {
        if self.status != TrialStatus::Active {
            return Err(SubscriptionError::InvalidState {
                action: "expire trial".to_string(),
                state: self.status.to_string(),
            });
        }
        self.status = TrialStatus::Expired;
        self.days_remaining = 0;
        Ok(())
    }

    /// Marks that the user was notified about upcoming trial expiration.
    pub fn mark_expiration_notified(&mut self) {
        self.expiration_notified = true;
    }

    /// Updates the days remaining based on the current time.
    pub fn update_days_remaining(&mut self, now_ms: u64) {
        self.days_remaining = self.calculate_days_remaining(now_ms);
    }
}

// ---------------------------------------------------------------------------
// TrialManager
// ---------------------------------------------------------------------------

/// Manages trial lifecycle for all tenants.
///
/// Handles trial creation, expiration checking, and conversion.
pub struct TrialManager {
    /// Active trials indexed by tenant ID.
    trials: std::collections::HashMap<TenantId, Trial>,
}

impl TrialManager {
    /// Creates a new trial manager.
    pub fn new() -> Self {
        Self {
            trials: std::collections::HashMap::new(),
        }
    }

    /// Creates a 14-day trial for a tenant.
    ///
    /// Returns an error if the tenant already has an active or converted trial.
    pub fn create_trial(&mut self, tenant_id: TenantId, now_ms: u64) -> Result<Trial, SubscriptionError> {
        if let Some(existing) = self.trials.get(&tenant_id) {
            if existing.status == TrialStatus::Active || existing.status == TrialStatus::Converted {
                return Err(SubscriptionError::Validation(format!(
                    "tenant {} already has a {} trial",
                    tenant_id, existing.status
                )));
            }
        }

        let trial = Trial::new(tenant_id, now_ms);
        self.trials.insert(tenant_id, trial.clone());
        Ok(trial)
    }

    /// Returns the trial for a tenant, if any.
    pub fn get_trial(&self, tenant_id: &TenantId) -> Option<&Trial> {
        self.trials.get(tenant_id)
    }

    /// Returns a mutable reference to the trial for a tenant, if any.
    pub fn get_trial_mut(&mut self, tenant_id: &TenantId) -> Option<&mut Trial> {
        self.trials.get_mut(tenant_id)
    }

    /// Checks all active trials for expiration and expires them.
    ///
    /// Returns the list of tenant IDs whose trials were expired.
    pub fn check_expirations(&mut self, now_ms: u64) -> Vec<TenantId> {
        let mut expired = Vec::new();

        for (tenant_id, trial) in &mut self.trials {
            if trial.status == TrialStatus::Active && trial.is_expired_at(now_ms) {
                let _ = trial.expire();
                expired.push(*tenant_id);
            }
        }

        expired
    }

    /// Finds trials that will expire within the given number of days.
    ///
    /// Used for sending expiration warning notifications.
    pub fn find_expiring_soon(&self, now_ms: u64, within_days: u32) -> Vec<&Trial> {
        let threshold_ms = now_ms + (within_days as u64 * 24 * 60 * 60 * 1000);

        self.trials
            .values()
            .filter(|trial| {
                trial.status == TrialStatus::Active
                    && !trial.expiration_notified
                    && trial.expires_at_ms <= threshold_ms
            })
            .collect()
    }

    /// Converts a trial to a paid subscription.
    pub fn convert_trial(&mut self, tenant_id: &TenantId, now_ms: u64) -> Result<Trial, SubscriptionError> {
        let trial = self.trials.get_mut(tenant_id).ok_or_else(|| {
            SubscriptionError::Validation(format!("no trial found for tenant {}", tenant_id))
        })?;

        trial.convert(now_ms)?;
        Ok(trial.clone())
    }

    /// Returns the number of active trials.
    pub fn active_trial_count(&self) -> usize {
        self.trials.values().filter(|t| t.status == TrialStatus::Active).count()
    }

    /// Returns the total number of trials.
    pub fn total_trial_count(&self) -> usize {
        self.trials.len()
    }
}

impl Default for TrialManager {
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
    fn trial_new() {
        let trial = Trial::new(TenantId::new(), 1000);
        assert_eq!(trial.status, TrialStatus::Active);
        assert_eq!(trial.days_remaining, 14);
        assert!(!trial.is_expired_at(1000));
    }

    #[test]
    fn trial_expiration() {
        let trial = Trial::new(TenantId::new(), 1000);
        let expiration_ms = 1000 + TRIAL_DURATION_MS;
        assert!(trial.is_expired_at(expiration_ms));
        assert!(trial.is_expired_at(expiration_ms + 1));
    }

    #[test]
    fn trial_days_remaining() {
        let trial = Trial::new(TenantId::new(), 0);
        assert_eq!(trial.calculate_days_remaining(0), 14);
        assert_eq!(trial.calculate_days_remaining(7 * 24 * 60 * 60 * 1000), 7);
        assert_eq!(trial.calculate_days_remaining(TRIAL_DURATION_MS), 0);
    }

    #[test]
    fn trial_convert() {
        let mut trial = Trial::new(TenantId::new(), 1000);
        trial.convert(5000).expect("convert");
        assert_eq!(trial.status, TrialStatus::Converted);
        assert_eq!(trial.converted_at_ms, Some(5000));
    }

    #[test]
    fn trial_convert_not_active_fails() {
        let mut trial = Trial::new(TenantId::new(), 1000);
        trial.expire().expect("expire");
        let result = trial.convert(5000);
        assert!(result.is_err());
    }

    #[test]
    fn trial_cancel() {
        let mut trial = Trial::new(TenantId::new(), 1000);
        trial.cancel(2000).expect("cancel");
        assert_eq!(trial.status, TrialStatus::Cancelled);
    }

    #[test]
    fn trial_expire() {
        let mut trial = Trial::new(TenantId::new(), 1000);
        trial.expire().expect("expire");
        assert_eq!(trial.status, TrialStatus::Expired);
    }

    #[test]
    fn trial_manager_create() {
        let mut mgr = TrialManager::new();
        let tenant = TenantId::new();
        let trial = mgr.create_trial(tenant, 1000).expect("create");
        assert_eq!(trial.status, TrialStatus::Active);
        assert_eq!(mgr.active_trial_count(), 1);
    }

    #[test]
    fn trial_manager_duplicate_fails() {
        let mut mgr = TrialManager::new();
        let tenant = TenantId::new();
        mgr.create_trial(tenant, 1000).expect("create");
        let result = mgr.create_trial(tenant, 2000);
        assert!(result.is_err());
    }

    #[test]
    fn trial_manager_check_expirations() {
        let mut mgr = TrialManager::new();
        let tenant = TenantId::new();
        mgr.create_trial(tenant, 1000).expect("create");

        let expired = mgr.check_expirations(1000 + TRIAL_DURATION_MS);
        assert_eq!(expired.len(), 1);
        assert_eq!(expired[0], tenant);
    }

    #[test]
    fn trial_manager_find_expiring_soon() {
        let mut mgr = TrialManager::new();
        let tenant = TenantId::new();
        mgr.create_trial(tenant, 0).expect("create");

        // Within 7 days from now (trial started at 0, expires at 14 days)
        let expiring = mgr.find_expiring_soon(7 * 24 * 60 * 60 * 1000, 7);
        assert_eq!(expiring.len(), 1);
    }

    #[test]
    fn trial_manager_convert() {
        let mut mgr = TrialManager::new();
        let tenant = TenantId::new();
        mgr.create_trial(tenant, 1000).expect("create");

        let trial = mgr.convert_trial(&tenant, 5000).expect("convert");
        assert_eq!(trial.status, TrialStatus::Converted);
    }
}
