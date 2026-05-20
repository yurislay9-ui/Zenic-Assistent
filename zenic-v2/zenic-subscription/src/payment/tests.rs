//! Payment module tests.

#[cfg(test)]
mod tests {
    use super::super::types::{
        UsdtPayment, UsdtPaymentMethod, PaymentStatus, PaymentVerification,
        PAYMENT_EXPIRY_MS,
    };
    use zenic_proto::{PaymentId, SubscriptionId, TenantId};

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
    fn payment_verification_valid() {
        let verification = PaymentVerification::valid(
            PaymentId::new(),
            99_000_000, // 99 USDT in smallest unit (6 decimals)
            valid_wallet(),
            valid_wallet(),
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
