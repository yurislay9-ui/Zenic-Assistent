//! USDT TRC20 payment processor: the core `UsdtPayment` state machine.

use serde::{Deserialize, Serialize};
use zenic_proto::{PaymentId, SubscriptionId, TenantId};

use crate::errors::SubscriptionError;
use super::types::{UsdtPaymentMethod, PaymentStatus, PAYMENT_EXPIRY_MS, MAX_VERIFICATION_ATTEMPTS};

// ---------------------------------------------------------------------------
// UsdtPayment
// ---------------------------------------------------------------------------

/// A USDT TRC20 payment for a subscription.
///
/// Contains all information needed for manual/semi-manual payment processing,
/// including the TRON transaction hash and wallet addresses.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UsdtPayment {
    /// Unique payment identifier.
    pub id: PaymentId,
    /// The subscription this payment is for.
    pub subscription_id: SubscriptionId,
    /// The tenant making the payment.
    pub tenant_id: TenantId,
    /// Payment processing method.
    pub method: UsdtPaymentMethod,
    /// Current payment status.
    pub status: PaymentStatus,
    /// Amount in USDT TRC20.
    pub amount_usdt: u64,
    /// Whether this includes a setup fee.
    pub includes_setup_fee: bool,
    /// Setup fee amount in USDT (0 if not applicable).
    pub setup_fee_amount_usdt: u64,
    /// Destination wallet address (company's TRON wallet).
    pub destination_wallet: String,
    /// Source wallet address (customer's TRON wallet).
    pub source_wallet: Option<String>,
    /// TRON blockchain transaction hash.
    pub tx_hash: Option<String>,
    /// Block number of the transaction (for verification).
    pub block_number: Option<u64>,
    /// When the payment was created (ms since epoch).
    pub created_at_ms: u64,
    /// When the payment was confirmed (ms since epoch).
    pub confirmed_at_ms: Option<u64>,
    /// When the payment expired (ms since epoch).
    pub expired_at_ms: Option<u64>,
    /// Admin who verified the payment (for manual method).
    pub verified_by: Option<String>,
    /// Notes from the admin who verified.
    pub verification_notes: Option<String>,
    /// Number of confirmation attempts.
    pub verification_attempts: u32,
}

impl UsdtPayment {
    /// Creates a new pending USDT TRC20 payment.
    pub fn new(
        subscription_id: SubscriptionId,
        tenant_id: TenantId,
        amount_usdt: u64,
        method: UsdtPaymentMethod,
        destination_wallet: String,
        includes_setup_fee: bool,
        setup_fee_amount_usdt: u64,
        now_ms: u64,
    ) -> Self {
        Self {
            id: PaymentId::new(),
            subscription_id,
            tenant_id,
            method,
            status: PaymentStatus::PendingTransfer,
            amount_usdt,
            includes_setup_fee,
            setup_fee_amount_usdt,
            destination_wallet,
            source_wallet: None,
            tx_hash: None,
            block_number: None,
            created_at_ms: now_ms,
            confirmed_at_ms: None,
            expired_at_ms: None,
            verified_by: None,
            verification_notes: None,
            verification_attempts: 0,
        }
    }

    /// Submits a TRON transaction hash for verification.
    pub fn submit_tx_hash(
        &mut self,
        tx_hash: String,
        source_wallet: String,
        block_number: u64,
    ) -> Result<(), SubscriptionError> {
        if self.status != PaymentStatus::PendingTransfer {
            return Err(SubscriptionError::InvalidState {
                action: "submit tx hash".to_string(),
                state: self.status.to_string(),
            });
        }

        // Basic TRON tx hash validation (64 hex chars).
        if tx_hash.len() != 64 || !tx_hash.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err(SubscriptionError::InvalidTxHash(tx_hash));
        }

        // Basic TRON address validation (starts with 'T', 34 chars).
        if !source_wallet.starts_with('T') || source_wallet.len() != 34 {
            return Err(SubscriptionError::InvalidWalletAddress(source_wallet));
        }

        self.tx_hash = Some(tx_hash);
        self.source_wallet = Some(source_wallet);
        self.block_number = Some(block_number);
        self.status = PaymentStatus::PendingVerification;
        self.verification_attempts += 1;

        Ok(())
    }

    /// Confirms the payment (admin action for manual, or auto for semi-manual).
    pub fn confirm(
        &mut self,
        verified_by: String,
        notes: Option<String>,
        now_ms: u64,
    ) -> Result<(), SubscriptionError> {
        if self.status != PaymentStatus::PendingVerification {
            return Err(SubscriptionError::InvalidState {
                action: "confirm payment".to_string(),
                state: self.status.to_string(),
            });
        }

        self.status = PaymentStatus::Confirmed;
        self.confirmed_at_ms = Some(now_ms);
        self.verified_by = Some(verified_by);
        self.verification_notes = notes;

        Ok(())
    }

    /// Fails the payment after verification failed.
    pub fn fail(&mut self, reason: String) -> Result<(), SubscriptionError> {
        if !self.status.is_pending() {
            return Err(SubscriptionError::InvalidState {
                action: "fail payment".to_string(),
                state: self.status.to_string(),
            });
        }

        self.status = PaymentStatus::Failed;
        self.verification_notes = Some(reason);
        Ok(())
    }

    /// Refunds the payment (marks as refunded, actual refund is manual).
    pub fn refund(&mut self, notes: String) -> Result<(), SubscriptionError> {
        if self.status != PaymentStatus::Confirmed {
            return Err(SubscriptionError::InvalidState {
                action: "refund payment".to_string(),
                state: self.status.to_string(),
            });
        }

        self.status = PaymentStatus::Refunded;
        self.verification_notes = Some(notes);
        Ok(())
    }

    /// Marks the payment as expired.
    pub fn expire(&mut self, now_ms: u64) -> Result<(), SubscriptionError> {
        if self.status.is_terminal() {
            return Err(SubscriptionError::InvalidState {
                action: "expire payment".to_string(),
                state: self.status.to_string(),
            });
        }

        self.status = PaymentStatus::Expired;
        self.expired_at_ms = Some(now_ms);
        Ok(())
    }

    /// Whether the payment has expired based on time.
    pub fn is_expired_at(&self, now_ms: u64) -> bool {
        self.status.is_pending() && now_ms >= self.created_at_ms + PAYMENT_EXPIRY_MS
    }

    /// Whether more verification attempts are allowed.
    pub fn can_retry_verification(&self) -> bool {
        self.verification_attempts < MAX_VERIFICATION_ATTEMPTS
    }

    /// Increments the verification attempt counter.
    pub fn increment_verification_attempt(&mut self) {
        self.verification_attempts += 1;
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use zenic_proto::{SubscriptionId, TenantId};

    fn valid_wallet() -> String {
        "TXYZabcd1234abcd1234abcd1234abcd12".to_string() // 34 chars starting with T
    }

    fn valid_tx_hash() -> String {
        "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2".to_string() // 64 hex chars
    }

    #[test]
    fn payment_new() {
        let payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );
        assert_eq!(payment.status, PaymentStatus::PendingTransfer);
        assert_eq!(payment.amount_usdt, 99);
    }

    #[test]
    fn payment_submit_tx_hash() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::SemiManual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        payment
            .submit_tx_hash(valid_tx_hash(), valid_wallet(), 12345)
            .expect("submit");

        assert_eq!(payment.status, PaymentStatus::PendingVerification);
        assert_eq!(payment.tx_hash, Some(valid_tx_hash()));
        assert_eq!(payment.verification_attempts, 1);
    }

    #[test]
    fn payment_submit_invalid_tx_hash() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        let result = payment.submit_tx_hash("short".to_string(), valid_wallet(), 12345);
        assert!(result.is_err());
    }

    #[test]
    fn payment_submit_invalid_wallet() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        let result = payment.submit_tx_hash(valid_tx_hash(), "0xabc".to_string(), 12345);
        assert!(result.is_err());
    }

    #[test]
    fn payment_confirm() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        payment
            .submit_tx_hash(valid_tx_hash(), valid_wallet(), 12345)
            .expect("submit");
        payment
            .confirm("admin".to_string(), Some("Verified".to_string()), 2000)
            .expect("confirm");

        assert_eq!(payment.status, PaymentStatus::Confirmed);
        assert_eq!(payment.verified_by, Some("admin".to_string()));
    }

    #[test]
    fn payment_confirm_without_tx_fails() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        let result = payment.confirm("admin".to_string(), None, 2000);
        assert!(result.is_err());
    }

    #[test]
    fn payment_fail() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        payment
            .submit_tx_hash(valid_tx_hash(), valid_wallet(), 12345)
            .expect("submit");
        payment.fail("Amount mismatch".to_string()).expect("fail");

        assert_eq!(payment.status, PaymentStatus::Failed);
    }

    #[test]
    fn payment_refund() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        payment
            .submit_tx_hash(valid_tx_hash(), valid_wallet(), 12345)
            .expect("submit");
        payment.confirm("admin".to_string(), None, 2000).expect("confirm");
        payment.refund("Customer request".to_string()).expect("refund");

        assert_eq!(payment.status, PaymentStatus::Refunded);
    }

    #[test]
    fn payment_expire() {
        let mut payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        payment.expire(5000).expect("expire");
        assert_eq!(payment.status, PaymentStatus::Expired);
    }

    #[test]
    fn payment_is_expired_at() {
        let payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            99,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            false,
            0,
            1000,
        );

        assert!(!payment.is_expired_at(1000));
        assert!(payment.is_expired_at(1000 + PAYMENT_EXPIRY_MS));
    }

    #[test]
    fn payment_on_premise_with_setup_fee() {
        let payment = UsdtPayment::new(
            SubscriptionId::new(),
            TenantId::new(),
            799,
            UsdtPaymentMethod::Manual,
            valid_wallet(),
            true,
            2000,
            1000,
        );
        assert!(payment.includes_setup_fee);
        assert_eq!(payment.setup_fee_amount_usdt, 2000);
    }
}
