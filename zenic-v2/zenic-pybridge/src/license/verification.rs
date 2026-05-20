//! License verification — verify_license public API.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use std::fs;

use super::crypto::{constant_time_compare, hex_decode, hex_encode, hmac_sha256};
use super::types::{current_unix_timestamp, LicenseTier};

/// Verify a license JSON payload against a cryptographic key.
///
/// Parameters
/// ----------
/// license_json : str
///     JSON string containing the license data.
/// public_key : str
///     HMAC secret key for signature verification.
///
/// Returns
/// -------
/// dict
///     ``{"is_valid": bool, "status": str, "tier": str,
///      "expires_at": int, "days_remaining": int, "error": str}``
#[pyfunction]
#[pyo3(signature = (license_json, public_key))]
pub fn verify_license(
    py: Python<'_>,
    license_json: &str,
    public_key: &str,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    // 1. Parse JSON
    let parsed: serde_json::Value = match serde_json::from_str(license_json) {
        Ok(v) => v,
        Err(e) => {
            result.set_item("is_valid", false)?;
            result.set_item("status", "invalid")?;
            result.set_item("tier", "community")?;
            result.set_item("expires_at", 0)?;
            result.set_item("days_remaining", 0)?;
            result.set_item("error", format!("JSON parse error: {}", e))?;
            return Ok(result.unbind());
        }
    };

    // Helper closures
    let get_str = |obj: &serde_json::Value, keys: &[&str]| -> String {
        for key in keys {
            if let Some(val) = obj.get(key).and_then(|v| v.as_str()) {
                return val.to_string();
            }
        }
        String::new()
    };

    let get_i64 = |obj: &serde_json::Value, key: &str| -> i64 {
        obj.get(key).and_then(|v| v.as_i64()).unwrap_or(0)
    };

    let get_u32 = |obj: &serde_json::Value, key: &str| -> u32 {
        obj.get(key).and_then(|v| v.as_u64()).unwrap_or(1) as u32
    };

    // 2. Extract fields
    let license_key = get_str(&parsed, &["license_key", "license_id"]);
    let tier_str = get_str(&parsed, &["tier"]);
    let holder = get_str(&parsed, &["holder", "issued_to"]);
    let issued_at = get_i64(&parsed, "issued_at");
    let expires_at = get_i64(&parsed, "expires_at");
    let hardware_id = get_str(&parsed, &["hardware_id"]);
    let max_users = get_u32(&parsed, "max_users");
    let signature = get_str(&parsed, &["signature"]);

    let features: Vec<String> = parsed
        .get("features")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let tier = LicenseTier::from_str(&tier_str);

    // 3. Reconstruct canonical signable data
    let mut sorted_features = features.clone();
    sorted_features.sort();
    let signable_parts = [
        license_key.as_str(),
        tier.as_str(),
        holder.as_str(),
        &issued_at.to_string(),
        &expires_at.to_string(),
        &sorted_features.join(","),
        &max_users.to_string(),
        hardware_id.as_str(),
    ];
    let signable_data = signable_parts.join("|");

    // 4. Verify HMAC-SHA256 signature
    let expected_hmac = hmac_sha256(public_key.as_bytes(), signable_data.as_bytes());
    let expected_hex = hex_encode(&expected_hmac);

    let sig_valid = if signature.len() == expected_hex.len() {
        constant_time_compare(signature.as_bytes(), expected_hex.as_bytes())
    } else {
        match hex_decode(&signature) {
            Ok(sig_bytes) => constant_time_compare(&sig_bytes, &expected_hmac),
            Err(_) => false,
        }
    };

    if !sig_valid {
        result.set_item("is_valid", false)?;
        result.set_item("status", "invalid")?;
        result.set_item("tier", tier.as_str())?;
        result.set_item("expires_at", expires_at)?;
        result.set_item("days_remaining", 0)?;
        result.set_item("error", "Invalid signature")?;
        return Ok(result.unbind());
    }

    // 5. Check expiration
    let now = current_unix_timestamp();
    let (is_valid, status, days_remaining) = if expires_at == 0 {
        (true, "valid", i64::MAX)
    } else if now > expires_at {
        let hours_expired = (now - expires_at) / 3600;
        if hours_expired <= 72 {
            let days_rem = ((expires_at - now) / 86400).max(0);
            (true, "grace_period", days_rem)
        } else {
            (false, "expired", 0)
        }
    } else {
        let days_rem = (expires_at - now) / 86400;
        (true, "valid", days_rem)
    };

    result.set_item("is_valid", is_valid)?;
    result.set_item("status", status)?;
    result.set_item("tier", tier.as_str())?;
    result.set_item("expires_at", expires_at)?;
    result.set_item("days_remaining", days_remaining)?;
    result.set_item("error", "")?;

    Ok(result.unbind())
}

/// Check files for tampering by comparing current BLAKE3 hashes with expected values.
///
/// Parameters
/// ----------
/// check_paths : list[str]
///     File paths to check.
/// expected_hashes : list[str]
///     Expected BLAKE3 hex hashes for each path (same order).
///
/// Returns
/// -------
/// dict
///     ``{"is_tampered": bool, "checked_files": int,
///      "tampered_files": list[str], "details": list[dict]}``
#[pyfunction]
#[pyo3(signature = (check_paths, expected_hashes))]
pub fn check_tampering(
    py: Python<'_>,
    check_paths: Vec<String>,
    expected_hashes: Vec<String>,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    if check_paths.len() != expected_hashes.len() {
        return Err(PyValueError::new_err(
            "check_paths and expected_hashes must have the same length",
        ));
    }

    let mut tampered_files: Vec<String> = Vec::new();
    let details = PyList::empty_bound(py);
    let mut checked_count: i32 = 0;

    for (path, expected_hash) in check_paths.iter().zip(expected_hashes.iter()) {
        checked_count += 1;
        let detail = PyDict::new_bound(py);

        detail.set_item("path", path)?;
        detail.set_item("expected_hash", expected_hash)?;

        match fs::read(path) {
            Ok(data) => {
                let current_hash = blake3::hash(&data).to_hex().to_string();
                detail.set_item("current_hash", &current_hash)?;

                let is_tampered = !constant_time_compare(
                    current_hash.as_bytes(),
                    expected_hash.as_bytes(),
                );
                detail.set_item("is_tampered", is_tampered)?;
                detail.set_item("error", "")?;

                if is_tampered {
                    tampered_files.push(path.clone());
                }
            }
            Err(e) => {
                detail.set_item("current_hash", "")?;
                detail.set_item("is_tampered", true)?;
                detail.set_item("error", e.to_string())?;
                tampered_files.push(path.clone());
            }
        }

        details.append(detail.as_any())?;
    }

    result.set_item("is_tampered", !tampered_files.is_empty())?;
    result.set_item("checked_files", checked_count)?;
    result.set_item("tampered_files", tampered_files)?;
    result.set_item("details", details)?;

    Ok(result.unbind())
}
