//! Licensing & Anti-tampering — Security-critical operations for Zenic-Agents.
//!
//! This module implements the licensing system core in Rust for:
//! - Cryptographic license verification (HMAC-SHA256 signatures)
//! - Hardware fingerprint generation (BLAKE3-hashed system identifiers)
//! - Constant-time hardware binding comparison (timing-attack resistant)
//! - File integrity / anti-tampering checks (BLAKE3 hashes)
//! - Remote kill-switch connectivity check (TCP with timeout + grace period)
//!
//! Rust is ideal for these security-critical operations because:
//! - License verification is on the trust boundary — any bypass = revenue loss
//! - Constant-time comparison prevents timing side-channels
//! - BLAKE3 hashing is significantly faster than SHA-256 for fingerprints
//! - Anti-tampering checks must be tamper-resistant at the binary level
//! - The Rust type system enforces invariants that Python cannot

pub mod crypto;
pub mod hardware;
pub mod kill_switch;
pub mod signing;
pub mod types;
pub mod verification;

// Re-export all public types and functions so that `use crate::license::LicenseTier` still works
pub use crypto::{constant_time_compare, hex_decode, hex_encode, hmac_sha256};
pub use hardware::{collect_hw_components, generate_hardware_fingerprint, verify_hardware_binding};
pub use kill_switch::{check_kill_switch, parse_host_port};
pub use signing::{sign_data, verify_signature};
pub use types::{current_unix_timestamp, LicenseInfo, LicenseStatus, LicenseTier};
pub use verification::{check_tampering, verify_license};

// ═══════════════════════════════════════════════════════════════
//  Unit tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_license_tier_str_roundtrip() {
        assert_eq!(LicenseTier::Starter.as_str(), "starter");
        assert_eq!(LicenseTier::Business.as_str(), "business");
        assert_eq!(LicenseTier::Enterprise.as_str(), "enterprise");
        assert_eq!(LicenseTier::OnPremiseEnterprise.as_str(), "on_premise_enterprise");
        assert_eq!(LicenseTier::Trial.as_str(), "trial");
    }

    #[test]
    fn test_license_tier_from_str() {
        assert_eq!(LicenseTier::from_str("starter"), LicenseTier::Starter);
        assert_eq!(LicenseTier::from_str("community"), LicenseTier::Starter);
        assert_eq!(LicenseTier::from_str("free"), LicenseTier::Starter);
        assert_eq!(LicenseTier::from_str("business"), LicenseTier::Business);
        assert_eq!(LicenseTier::from_str("professional"), LicenseTier::Business);
        assert_eq!(LicenseTier::from_str("pro"), LicenseTier::Business);
        assert_eq!(LicenseTier::from_str("enterprise"), LicenseTier::Enterprise);
        assert_eq!(LicenseTier::from_str("on_premise_enterprise"), LicenseTier::OnPremiseEnterprise);
        assert_eq!(LicenseTier::from_str("whitelabel"), LicenseTier::OnPremiseEnterprise);
        assert_eq!(LicenseTier::from_str("trial"), LicenseTier::Trial);
        assert_eq!(LicenseTier::from_str("unknown"), LicenseTier::Starter);
    }

    #[test]
    fn test_license_status_str_roundtrip() {
        assert_eq!(LicenseStatus::Valid.as_str(), "valid");
        assert_eq!(LicenseStatus::Expired.as_str(), "expired");
        assert_eq!(LicenseStatus::Invalid.as_str(), "invalid");
        assert_eq!(LicenseStatus::Revoked.as_str(), "revoked");
        assert_eq!(LicenseStatus::GracePeriod.as_str(), "grace_period");
    }

    #[test]
    fn test_license_status_from_str() {
        assert_eq!(LicenseStatus::from_str("valid"), LicenseStatus::Valid);
        assert_eq!(LicenseStatus::from_str("active"), LicenseStatus::Valid);
        assert_eq!(LicenseStatus::from_str("expired"), LicenseStatus::Expired);
        assert_eq!(LicenseStatus::from_str("invalid"), LicenseStatus::Invalid);
        assert_eq!(LicenseStatus::from_str("revoked"), LicenseStatus::Revoked);
        assert_eq!(LicenseStatus::from_str("grace_period"), LicenseStatus::GracePeriod);
    }

    #[test]
    fn test_signable_data_deterministic() {
        let info = LicenseInfo {
            license_key: "zl-abc123".to_string(),
            tier: LicenseTier::Business,
            holder: "Test Org".to_string(),
            issued_at: 1700000000,
            expires_at: 1800000000,
            hardware_id: "hw123".to_string(),
            features: vec!["b".to_string(), "a".to_string()],
            max_users: 5,
            signature: String::new(),
        };
        let data1 = info.to_signable_data();
        let data2 = info.to_signable_data();
        assert_eq!(data1, data2);
        // Features should be sorted
        assert!(data1.contains("a,b"));
    }

    #[test]
    fn test_hmac_sha256_basic() {
        let result = hmac_sha256(b"key", b"data");
        assert_eq!(result.len(), 32);
    }

    #[test]
    fn test_hex_roundtrip() {
        let bytes: Vec<u8> = vec![0x00, 0x01, 0xff, 0xab, 0xcd];
        let encoded = hex_encode(&bytes);
        assert_eq!(encoded, "0001ffabcd");
        let decoded = hex_decode(&encoded).unwrap();
        assert_eq!(decoded, bytes);
    }

    #[test]
    fn test_constant_time_compare() {
        assert!(constant_time_compare(b"hello", b"hello"));
        assert!(!constant_time_compare(b"hello", b"world"));
        assert!(!constant_time_compare(b"hello", b"hella"));
        assert!(!constant_time_compare(b"short", b"longer"));
    }

    #[test]
    fn test_sign_and_verify() {
        let data = "test-license-data";
        let key = "secret-key-123";
        let sig = sign_data(data, key).unwrap();
        assert!(verify_signature(data, &sig, key).unwrap());
        assert!(!verify_signature(data, &sig, "wrong-key").unwrap());
        assert!(!verify_signature("wrong-data", &sig, key).unwrap());
    }

    #[test]
    fn test_parse_host_port() {
        assert_eq!(parse_host_port("http://example.com:8080/path"), Some(("example.com".to_string(), 8080)));
        assert_eq!(parse_host_port("https://example.com/path"), Some(("example.com".to_string(), 443)));
        assert_eq!(parse_host_port("http://example.com"), Some(("example.com".to_string(), 80)));
        assert_eq!(parse_host_port(""), None);
    }

    #[test]
    fn test_collect_hw_components() {
        let components = collect_hw_components();
        assert!(!components.is_empty());
    }
}
