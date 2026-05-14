//! Cryptographic operations for Zenic-Agents.
//!
//! Provides PBKDF2 key derivation, Argon2id hashing, and constant-time
//! comparison for secure credential handling.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

use hmac::{Hmac, Mac};
use sha2::Sha256;

/// Derive a cryptographic key using PBKDF2-HMAC-SHA256.
///
/// Parameters
/// ----------
/// password : bytes
///     The password to derive the key from.
/// salt : bytes
///     Cryptographic salt (recommended: >= 16 bytes).
/// iterations : int
///     Number of PBKDF2 iterations (recommended: >= 600,000).
/// key_length : int
///     Desired output key length in bytes.
///
/// Returns
/// -------
/// bytes
///     The derived key.
///
/// Raises
/// ------
/// ValueError
///     If iterations or key_length are non-positive, or if password/salt
///     are empty.
#[pyfunction]
#[pyo3(signature = (password, salt, iterations, key_length))]
pub fn pbkdf2_derive_key<'py>(
    py: Python<'py>,
    password: &[u8],
    salt: &[u8],
    iterations: u32,
    key_length: usize,
) -> PyResult<Bound<'py, PyBytes>> {
    if password.is_empty() {
        return Err(PyValueError::new_err("password must not be empty"));
    }
    if salt.is_empty() {
        return Err(PyValueError::new_err("salt must not be empty"));
    }
    if iterations == 0 {
        return Err(PyValueError::new_err("iterations must be positive"));
    }
    if key_length == 0 {
        return Err(PyValueError::new_err("key_length must be positive"));
    }

    // PBKDF2-HMAC-SHA256 implementation
    let hmac_len = 32usize; // SHA-256 output length
    let num_blocks = (key_length + hmac_len - 1) / hmac_len;

    let mut derived = Vec::with_capacity(num_blocks * hmac_len);

    for block_idx in 1..=num_blocks {
        // U_1 = HMAC(password, salt || INT_32_BE(block_idx))
        let mut mac = Hmac::<Sha256>::new_from_slice(password)
            .map_err(|e| PyValueError::new_err(format!("HMAC init error: {}", e)))?;
        mac.update(salt);
        mac.update(&(block_idx as u32).to_be_bytes());
        let mut u = mac.finalize().into_bytes();
        let mut result = u;

        // U_2 .. U_c
        for _ in 1..iterations {
            let mut mac = Hmac::<Sha256>::new_from_slice(password)
                .map_err(|e| PyValueError::new_err(format!("HMAC init error: {}", e)))?;
            mac.update(&u);
            u = mac.finalize().into_bytes();
            for (r, u_byte) in result.iter_mut().zip(u.iter()) {
                *r ^= u_byte;
            }
        }

        derived.extend_from_slice(&result);
    }

    derived.truncate(key_length);
    Ok(PyBytes::new_bound(py, &derived))
}

/// Hash a password using Argon2id.
///
/// Parameters
/// ----------
/// password : bytes
///     The password to hash.
/// salt : bytes
///     Cryptographic salt (recommended: >= 16 bytes).
/// memory_cost : int
///     Memory cost in KiB (default recommendation: 65536 = 64 MB).
/// time_cost : int
///     Number of passes (default recommendation: 3).
/// parallelism : int
///     Degree of parallelism (default recommendation: 4).
///
/// Returns
/// -------
/// bytes
///     The raw 32-byte Argon2id hash.
///
/// Raises
/// ------
/// ValueError
///     If parameters are invalid or hashing fails.
#[pyfunction]
#[pyo3(signature = (password, salt, memory_cost, time_cost, parallelism))]
pub fn argon2id_hash<'py>(
    py: Python<'py>,
    password: &[u8],
    salt: &[u8],
    memory_cost: u32,
    time_cost: u32,
    parallelism: u32,
) -> PyResult<Bound<'py, PyBytes>> {
    use argon2::{Algorithm, Argon2, Params, Version};

    if password.is_empty() {
        return Err(PyValueError::new_err("password must not be empty"));
    }
    if salt.is_empty() {
        return Err(PyValueError::new_err("salt must not be empty"));
    }
    if memory_cost == 0 {
        return Err(PyValueError::new_err("memory_cost must be positive"));
    }
    if time_cost == 0 {
        return Err(PyValueError::new_err("time_cost must be positive"));
    }
    if parallelism == 0 {
        return Err(PyValueError::new_err("parallelism must be positive"));
    }

    let params = Params::new(memory_cost, time_cost, parallelism, Some(32))
        .map_err(|e| PyValueError::new_err(format!("Invalid Argon2 parameters: {}", e)))?;

    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, params);

    let mut output = [0u8; 32];
    argon2
        .hash_password_into(password, salt, &mut output)
        .map_err(|e| PyValueError::new_err(format!("Argon2id hashing error: {}", e)))?;

    Ok(PyBytes::new_bound(py, &output))
}

/// Compare two byte strings in constant time.
///
/// This function runs in O(len(a)) time regardless of where the first
/// difference occurs, preventing timing side-channel attacks.
///
/// Parameters
/// ----------
/// a : bytes
///     First byte string.
/// b : bytes
///     Second byte string.
///
/// Returns
/// -------
/// bool
///     True if a and b are equal, False otherwise.
#[pyfunction]
#[pyo3(signature = (a, b))]
pub fn constant_time_compare(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }

    let mut result: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        result |= x ^ y;
    }
    result == 0
}

// ── Unit tests ──────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pbkdf2_hmac_logic() {
        // Test the core PBKDF2-HMAC-SHA256 logic directly without PyO3
        let password = b"password";
        let salt = b"salt";
        let hmac_len = 32usize;
        let key_length = 32usize;
        let iterations = 1u32;
        let num_blocks = (key_length + hmac_len - 1) / hmac_len;

        let mut derived = Vec::with_capacity(num_blocks * hmac_len);
        for block_idx in 1..=num_blocks {
            let mut mac = Hmac::<Sha256>::new_from_slice(password).unwrap();
            mac.update(salt);
            mac.update(&(block_idx as u32).to_be_bytes());
            let mut u = mac.finalize().into_bytes();
            let mut result = u;
            for _ in 1..iterations {
                let mut mac = Hmac::<Sha256>::new_from_slice(password).unwrap();
                mac.update(&u);
                u = mac.finalize().into_bytes();
                for (r, u_byte) in result.iter_mut().zip(u.iter()) {
                    *r ^= u_byte;
                }
            }
            derived.extend_from_slice(&result);
        }
        derived.truncate(key_length);
        assert_eq!(derived.len(), 32);
        assert_ne!(derived, [0u8; 32]); // Should not be all zeros
    }

    #[test]
    fn test_constant_time_compare_equal() {
        assert!(constant_time_compare(b"hello", b"hello"));
    }

    #[test]
    fn test_constant_time_compare_not_equal() {
        assert!(!constant_time_compare(b"hello", b"world"));
    }

    #[test]
    fn test_constant_time_compare_different_lengths() {
        assert!(!constant_time_compare(b"hello", b"helloworld"));
    }
}
