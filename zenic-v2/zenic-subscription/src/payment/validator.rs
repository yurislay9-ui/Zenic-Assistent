//! Payment verification: on-chain verification result types and tests.

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::super::types::PaymentVerification;
    use zenic_proto::PaymentId;

    #[test]
    fn payment_verification_valid() {
        let verification = PaymentVerification::valid(
            PaymentId::new(),
            99_000_000, // 99 USDT in smallest unit (6 decimals)
            "TXYZabcd1234abcd1234abcd1234abcd12".to_string(),
            "TXYZabcd1234abcd1234abcd1234abcd12".to_string(),
            20,
        );
        assert!(verification.is_valid);
        assert!(verification.failure_reason.is_none());
    }

    #[test]
    fn payment_verification_invalid() {
        let verification = PaymentVerification::invalid(
            PaymentId::new(),
            "Amount mismatch".to_string(),
        );
        assert!(!verification.is_valid);
        assert!(verification.failure_reason.is_some());
    }
}
