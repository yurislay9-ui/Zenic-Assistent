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
    let expected_hex = hex_encode(&expected);

    if signature.len() == expected_hex.len() {
        return Ok(constant_time_compare(
            signature.as_bytes(),
            expected_hex.as_bytes(),
        ));
    }

    match hex_decode(signature) {
        Ok(sig_bytes) => Ok(constant_time_compare(&sig_bytes, &expected)),
        Err(_) => Ok(false),
    }
}
