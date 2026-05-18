//! Subscription engine types: core struct definition and constructor.

use std::collections::HashMap;

use zenic_proto::{PaymentId, TenantId};

use crate::payment::UsdtPaymentMethod;
use crate::trial::TrialManager;
use crate::usage::UsageMeter;

// ---------------------------------------------------------------------------
// SubscriptionEngine
// ---------------------------------------------------------------------------

/// Main orchestrator for the subscription system.
///
/// Coordinates all subscription operations using the Saga pattern
/// for transactional reliability. All payments are USDT TRC20 only.
pub struct SubscriptionEngine {
    /// Active subscriptions indexed by tenant ID.
    pub(crate) subscriptions: HashMap<TenantId, crate::types::Subscription>,

    /// Trial manager.
    pub(crate) trial_manager: TrialManager,

    /// Usage metering.
    pub(crate) usage_meter: UsageMeter,

    /// USDT TRC20 payments indexed by payment ID.
    pub(crate) payments: HashMap<PaymentId, crate::payment::UsdtPayment>,

    /// Company USDT TRC20 wallet address for receiving payments.
    pub(crate) company_wallet: String,

    /// Default payment processing method.
    pub(crate) default_payment_method: UsdtPaymentMethod,
}

impl SubscriptionEngine {
    /// Creates a new subscription engine.
    pub fn new(
        company_wallet: String,
        default_payment_method: UsdtPaymentMethod,
    ) -> Self {
        Self {
            subscriptions: HashMap::new(),
            trial_manager: TrialManager::new(),
            usage_meter: UsageMeter::new(),
            payments: HashMap::new(),
            company_wallet,
            default_payment_method,
        }
    }
}
