//! USDT TRC20 payment model: manual and semi-manual payment processing.
//!
//! All payments are in **USDT TRC20** only. No other payment methods are supported.
//! Payments are processed manually or semi-manually (no automated Stripe-like flow).

pub mod processor;
pub mod types;
pub mod validator;

// Re-export all public API so that `payment::UsdtPayment` etc.
// continue to work without changes in the parent lib.rs.
pub use types::{UsdtPaymentMethod, PaymentStatus, PaymentVerification};
pub use types::{PAYMENT_EXPIRY_DAYS, PAYMENT_EXPIRY_MS, MAX_VERIFICATION_ATTEMPTS};
pub use processor::UsdtPayment;
