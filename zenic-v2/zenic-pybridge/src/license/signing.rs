//! Signing and signature verification — PyO3-exposed sign_data and verify_signature.

use pyo3::prelude::*;

use super::crypto::{constant_time_compare, hex_decode, hex_encode, hmac_sha256};

/// Sign data using HMAC-SHA256.
///
/// Parameters
/// ----------
/// data : str
///     The data to sign.
/// secret_key : str
///     The secret key for the HMAC.
///
/// Returns
/// -------
/// str
///     Hex-encoded HMAC-SHA256 signature.
#[pyfunction]
#[pyo3(signature = (data, secret_key))]
pub fn sign_data(data: &str, secret_key: &str) -> PyResult<String> {
    let mac = hmac_sha256(secret_key.as_bytes(), data.as_bytes());
    Ok(hex_encode(&mac))
}

/// Verify an HMAC-SHA256 signature using constant-time comparison.
///
/// Parameters
/// ----------
/// data : str
///     The original data that was signed.
/// signature : str
///     The hex-encoded signature to verify.
/// secret_key : str
///     The secret key used for signing.
///
/// Returns
/// -------
/// bool
///     True if the signature is valid.
#[pyfunction]
#[pyo3(signature = (data, signature, secret_key))]
pub fn verify_signature(data: &str, signature: &str, secret_key: &str) -> PyResult<bool> {
    let expected = hmac_sha256(secret_key.as_bytes(), data.as_bytes());
    let expected_bytes = hex_decode(&hex_encode(&expected)).unwrap_or_default();
    let signature_bytes = hex_decode(signature)
        .unwrap_or_else(|_| {
            // Pad to expected length to avoid timing leak on length mismatch
            let len = expected_bytes.len().max(32);
            vec![0u8; len]
        });
    Ok(constant_time_compare(&expected_bytes, &signature_bytes))
}
