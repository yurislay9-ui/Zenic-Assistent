//! Shared types for the USDT TRC20 payment module.
//!
//! Contains the core enums, constants, and data structures used
//! across the payment sub-modules.

use serde::{Deserialize, Serialize};
use zenic_proto::PaymentId;

// ---------------------------------------------------------------------------
// UsdtPaymentMethod
// ---------------------------------------------------------------------------

/// How the payment is processed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum UsdtPaymentMethod {
    /// Fully manual: admin verifies the transaction and approves.
    Manual,
    /// Semi-manual: system pre-verifies the tx hash on TRON, admin confirms.
    SemiManual,
}

impl std::fmt::Display for UsdtPaymentMethod {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Manual => write!(f, "manual"),
            Self::SemiManual => write!(f, "semi_manual"),
        }
    }
}

// ---------------------------------------------------------------------------
// PaymentStatus
// ---------------------------------------------------------------------------

/// Status of a USDT TRC20 payment.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PaymentStatus {
    /// Payment initiated, awaiting USDT transfer.
    PendingTransfer,
    /// USDT transfer detected on-chain, awaiting verification.
    PendingVerification,
    /// Payment verified and confirmed.
    Confirmed,
    /// Payment verification failed (wrong amount, wrong address, etc.).
    Failed,
    /// Payment was refunded.
    Refunded,
    /// Payment expired (transfer never detected).
    Expired,
}

impl PaymentStatus {
    /// Whether the payment is in a pending state.
    pub fn is_pending(&self) -> bool {
        matches!(self, Self::PendingTransfer | Self::PendingVerification)
    }

    /// Whether the payment is in a terminal state.
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Confirmed | Self::Failed | Self::Refunded | Self::Expired)
    }
}

impl std::fmt::Display for PaymentStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::PendingTransfer => write!(f, "pending_transfer"),
            Self::PendingVerification => write!(f, "pending_verification"),
            Self::Confirmed => write!(f, "confirmed"),
            Self::Failed => write!(f, "failed"),
            Self::Refunded => write!(f, "refunded"),
            Self::Expired => write!(f, "expired"),
        }
    }
}

// ---------------------------------------------------------------------------
// PaymentVerification
// ---------------------------------------------------------------------------

/// Result of verifying a USDT TRC20 payment on the TRON blockchain.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PaymentVerification {
    /// The payment ID that was verified.
    pub payment_id: PaymentId,
    /// Whether the on-chain transaction was found.
    pub tx_found: bool,
    /// Verified amount in USDT (smallest unit, 6 decimals).
    pub verified_amount: u64,
    /// Verified destination address.
    pub verified_destination: String,
    /// Verified source address.
    pub verified_source: String,
    /// Block confirmation count.
    pub confirmations: u32,
    /// Whether the verification passed all checks.
    pub is_valid: bool,
    /// Failure reason if verification failed.
    pub failure_reason: Option<String>,
}

impl PaymentVerification {
    /// Creates a successful verification result.
    pub fn valid(
        payment_id: PaymentId,
        verified_amount: u64,
        verified_destination: String,
        verified_source: String,
        confirmations: u32,
    ) -> Self {
        Self {
            payment_id,
            tx_found: true,
            verified_amount,
            verified_destination,
            verified_source,
            confirmations,
            is_valid: true,
            failure_reason: None,
        }
    }

    /// Creates a failed verification result.
    pub fn invalid(payment_id: PaymentId, reason: String) -> Self {
        Self {
            payment_id,
            tx_found: false,
            verified_amount: 0,
            verified_destination: String::new(),
            verified_source: String::new(),
            confirmations: 0,
            is_valid: false,
            failure_reason: Some(reason),
        }
    }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Maximum number of days before a pending payment expires.
pub const PAYMENT_EXPIRY_DAYS: u64 = 3;

/// Duration before a pending payment expires in milliseconds.
pub const PAYMENT_EXPIRY_MS: u64 = PAYMENT_EXPIRY_DAYS * 24 * 60 * 60 * 1000;

/// Maximum verification attempts before marking as failed.
pub const MAX_VERIFICATION_ATTEMPTS: u32 = 5;
