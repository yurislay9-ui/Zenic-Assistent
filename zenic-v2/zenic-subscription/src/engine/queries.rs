//! Subscription queries: read-only accessors and trial expiration checks.

use zenic_proto::{PaymentId, TenantId};

use crate::payment::UsdtPayment;
use crate::types::SubscriptionStatus;

use super::types::SubscriptionEngine;

impl SubscriptionEngine {
    // -----------------------------------------------------------------------
    // Queries
    // -----------------------------------------------------------------------

    /// Returns the subscription for a tenant.
    pub fn get_subscription(&self, tenant_id: &TenantId) -> Option<&crate::types::Subscription> {
        self.subscriptions.get(tenant_id)
    }

    /// Returns the trial for a tenant.
    pub fn get_trial(&self, tenant_id: &TenantId) -> Option<&crate::trial::Trial> {
        self.trial_manager.get_trial(tenant_id)
    }

    /// Returns a payment by ID.
    pub fn get_payment(&self, payment_id: &PaymentId) -> Option<&UsdtPayment> {
        self.payments.get(payment_id)
    }

    /// Checks and expires overdue trials.
    pub fn check_trial_expirations(&mut self, now_ms: u64) -> Vec<TenantId> {
        let expired_tenants = self.trial_manager.check_expirations(now_ms);

        // Update subscription statuses for expired trials.
        for tenant_id in &expired_tenants {
            if let Some(subscription) = self.subscriptions.get_mut(tenant_id) {
                let _ = subscription.transition_to(SubscriptionStatus::Expired);
            }
        }

        expired_tenants
    }

    /// Returns the number of active subscriptions.
    pub fn active_subscription_count(&self) -> usize {
        self.subscriptions.values().filter(|s| s.has_access()).count()
    }

    /// Returns the total number of subscriptions.
    pub fn total_subscription_count(&self) -> usize {
        self.subscriptions.len()
    }

    /// Returns the number of active trials.
    pub fn active_trial_count(&self) -> usize {
        self.trial_manager.active_trial_count()
    }

    /// Returns the company's USDT TRC20 wallet address.
    pub fn company_wallet(&self) -> &str {
        &self.company_wallet
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::payment::UsdtPaymentMethod;
    use crate::types::SubscriptionStatus;
    use zenic_proto::TenantId;

    fn make_engine() -> SubscriptionEngine {
        SubscriptionEngine::new(
            "TCompanyWallet1234567890abcdefghijk".to_string(),
            UsdtPaymentMethod::Manual,
        )
    }

    #[test]
    fn engine_trial_expiration() {
        let mut engine = make_engine();
        let tenant = TenantId::new();

        engine.signup(tenant, 1000).expect("signup");

        // Expire the trial (14 days later).
        let expired = engine.check_trial_expirations(1000 + crate::trial::TRIAL_DURATION_MS);
        assert_eq!(expired.len(), 1);

        let subscription = engine.get_subscription(&tenant).expect("subscription");
        assert_eq!(subscription.status, SubscriptionStatus::Expired);
    }

    #[test]
    fn engine_company_wallet() {
        let engine = make_engine();
        assert!(engine.company_wallet().starts_with('T'));
    }
}
