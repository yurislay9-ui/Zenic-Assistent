use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::blueprint::*;
use super::config::*;
use super::helpers::*;
use super::types::*;

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Sign, Verify, Compute Hash, Validate Config
// ═══════════════════════════════════════════════════════════════

/// Sign a BlueprintConfig and produce a CertifiedBlueprint.
///
/// Uses the ECDSA signing capability from the license module to
/// create a tamper-proof signature over the canonical hash.
///
/// Parameters
/// ----------
/// config : BlueprintConfig
///     The blueprint configuration to sign.
/// private_key : str
///     The ECDSA private key in hex format (64 chars for secp256k1).
///
/// Returns
/// -------
/// CertifiedBlueprint
///     The signed blueprint with content_hash and signature.
#[pyfunction]
pub fn certifier_sign(
    config: &BlueprintConfig,
    private_key: &str,
) -> PyResult<CertifiedBlueprint> {
    if !config.is_certifiable() {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "BlueprintConfig is not certifiable. Missing required fields.",
        ));
    }

    let key_trimmed = private_key.trim();
    if key_trimmed.is_empty() {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "private_key cannot be empty",
        ));
    }

    // Compute canonical hash
    let content_hash = compute_canonical_hash(config);

    // Sign using the license module
    let signature = match crate::license::sign_data(key_trimmed, &content_hash) {
        Ok(sig) => sig,
        Err(e) => {
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                format!("ECDSA signing failed: {}", e),
            ));
        }
    };

    let blueprint_id = generate_blueprint_id(&config.niche_id);
    let certified_at = chrono::Utc::now().to_rfc3339();

    // Build initial audit chain
    let audit_chain = vec![
        AuditEntry {
            step: "config_created".to_string(),
            timestamp: certified_at.clone(),
            hash: content_hash.clone(),
            details: format!("BlueprintConfig created from niche '{}'", config.niche_id),
        },
        AuditEntry {
            step: "signed".to_string(),
            timestamp: certified_at.clone(),
            hash: content_hash.clone(),
            details: "ECDSA signature applied".to_string(),
        },
    ];

    Ok(CertifiedBlueprint {
        blueprint_id,
        config: config.clone(),
        status: CertificationStatus::Signed,
        content_hash,
        signature,
        signature_algorithm: "ecdsa-secp256k1".to_string(),
        certified_at,
        schema_version: CERTIFICATION_SCHEMA_VERSION.to_string(),
        audit_chain,
        warnings: Vec::new(),
        errors: Vec::new(),
    })
}

/// Verify a CertifiedBlueprint's ECDSA signature.
///
/// Parameters
/// ----------
/// blueprint : CertifiedBlueprint
///     The blueprint to verify.
/// public_key : str
///     The ECDSA public key in hex format.
///
/// Returns
/// -------
/// bool
///     True if the signature is valid, False otherwise.
#[pyfunction]
pub fn certifier_verify(blueprint: &CertifiedBlueprint, public_key: &str) -> bool {
    let key_trimmed = public_key.trim();
    if key_trimmed.is_empty() {
        return false;
    }

    // Recompute hash to verify content integrity
    let recomputed_hash = compute_canonical_hash(&blueprint.config);
    if recomputed_hash != blueprint.content_hash {
        return false;
    }

    // Verify ECDSA signature
    match crate::license::verify_signature(key_trimmed, &blueprint.content_hash, &blueprint.signature) {
        Ok(valid) => valid,
        Err(_) => false,
    }
}

/// Compute the canonical hash of a BlueprintConfig.
///
/// The hash is deterministic: same config always produces the
/// same hash, enabling integrity verification.
///
/// Parameters
/// ----------
/// config : BlueprintConfig
///     The configuration to hash.
///
/// Returns
/// -------
/// str
///     BLAKE3 hash string (64 hex characters).
#[pyfunction]
pub fn certifier_compute_hash(config: &BlueprintConfig) -> String {
    compute_canonical_hash(config)
}

/// Validate a BlueprintConfig for completeness.
///
/// Checks that all required fields are present and that the
/// configuration meets minimum certification requirements.
///
/// Parameters
/// ----------
/// config : BlueprintConfig
///     The configuration to validate.
///
/// Returns
/// -------
/// dict
///     Validation result with keys:
///     - ``valid`` (bool): True if certifiable
///     - ``errors`` (list[str]): Validation errors
///     - ``warnings`` (list[str]): Validation warnings
///     - ``compliance_count`` (int): Number of compliance standards
///     - ``db_tables`` (int): Number of DB table definitions
///     - ``monitors`` (int): Number of monitor definitions
///     - ``actions`` (int): Number of action definitions
#[pyfunction]
pub fn certifier_validate_config(config: &BlueprintConfig, py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new_bound(py);
    let mut errors: Vec<String> = Vec::new();
    let mut warnings_list: Vec<String> = Vec::new();

    if config.niche_id.is_empty() {
        errors.push("niche_id is required".to_string());
    }
    if config.business_name.is_empty() {
        errors.push("business_name is required".to_string());
    }
    if config.domain.is_empty() {
        errors.push("domain is required".to_string());
    }
    if config.data_sensitivity.is_empty() {
        errors.push("data_sensitivity is required".to_string());
    }

    if config.compliance.is_empty() {
        warnings_list.push("No compliance standards defined".to_string());
    }
    if config.db_schema.is_empty() {
        warnings_list.push("No database schema defined".to_string());
    }
    if config.monitors.is_empty() {
        warnings_list.push("No SNA monitors defined".to_string());
    }
    if config.actions.is_empty() {
        warnings_list.push("No executor actions defined".to_string());
    }

    // Check data sensitivity consistency
    if config.data_sensitivity == "critical" && config.compliance.is_empty() {
        errors.push("Critical data sensitivity requires at least one compliance standard".to_string());
    }

    dict.set_item("valid", errors.is_empty())?;
    dict.set_item("errors", errors)?;
    dict.set_item("warnings", warnings_list)?;
    dict.set_item("compliance_count", config.compliance.len())?;
    dict.set_item("db_tables", config.db_schema.len())?;
    dict.set_item("monitors", config.monitors.len())?;
    dict.set_item("actions", config.actions.len())?;
    Ok(dict.unbind())
}
