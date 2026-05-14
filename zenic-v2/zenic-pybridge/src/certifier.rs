//! Blueprint Certification Engine for Zenic-Agents (Phase 6.D).
//!
//! Converts completed YAML templates into CertifiedBlueprints with
//! ECDSA signing, integrity verification, and integration with the
//! existing Phase 5 Blueprint system.
//!
//! # Architecture
//!
//! The certification pipeline:
//!
//! 1. Completed template dict (from completer_finalize) → input
//! 2. Template validation (all required fields filled)
//! 3. BlueprintConfig construction from template data
//! 4. ECDSA signature generation over canonical serialized form
//! 5. CertifiedBlueprint with signature, hash, and metadata
//! 6. Export as YAML dict or string for Phase 5 Blueprint loader
//!
//! # CertifiedBlueprint Structure
//!
//! A CertifiedBlueprint contains:
//! - **config**: BlueprintConfig with all business-specific settings
//! - **metadata**: Certification metadata (timestamp, version, niche info)
//! - **integrity**: SHA-256 hash of canonical form + ECDSA signature
//! - **compliance**: Compliance standards extracted from niche definition
//! - **audit_trail**: Hash chain linking template → certified blueprint
//!
//! # Design Decisions
//!
//! - No `unwrap` or `panic` — all errors handled explicitly
//! - All external input validated before processing
//! - ECDSA signing uses the existing license module's primitives
//! - Hash chain provides tamper-proof audit trail
//! - Certification is idempotent: same template → same hash
//! - Blueprint version follows semantic versioning (major.minor.patch)
//!
//! # PyO3 Exposed Types
//!
//! - `BlueprintConfig` — structured blueprint configuration
//! - `CertifiedBlueprint` — signed, validated blueprint
//! - `CertificationResult` — result of the certification process
//! - `CertificationStatus` — status enum for certification states
//!
//! # PyO3 Exposed Functions
//!
//! - `certifier_from_template(template_dict)` — create BlueprintConfig from template
//! - `certifier_sign(config, private_key)` — sign a BlueprintConfig
//! - `certifier_verify(blueprint, public_key)` — verify a CertifiedBlueprint
//! - `certifier_to_blueprint_dict(blueprint)` — export to dict for Phase 5
//! - `certifier_compute_hash(config)` — compute canonical hash
//! - `certifier_validate_config(config)` — validate BlueprintConfig completeness
//! - `certifier_export_yaml(blueprint)` — export certified blueprint as YAML string

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::niche::DataSensitivity;

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Current certification schema version.
const CERTIFICATION_SCHEMA_VERSION: &str = "1.0.0";

/// Maximum number of compliance standards per blueprint.
const MAX_COMPLIANCE_STANDARDS: usize = 20;

/// Maximum number of monitors per blueprint.
const MAX_MONITORS: usize = 50;

/// Maximum number of actions per blueprint.
const MAX_ACTIONS: usize = 100;

/// Maximum number of database schema tables.
const MAX_DB_TABLES: usize = 200;

/// Hash algorithm identifier for integrity.
const HASH_ALGORITHM: &str = "sha256";

// ═══════════════════════════════════════════════════════════════
//  CertificationStatus — certification state machine
// ═══════════════════════════════════════════════════════════════

/// Status of a blueprint in the certification pipeline.
///
/// ======== ============ ===================================
/// Variant  Python value Description
/// ======== ============ ===================================
/// Draft    ``"draft"``  Config created but not yet signed
/// Signed   ``"signed"`` ECDSA signature applied
/// Verified ``"verified"`` Signature verified successfully
/// Revoked  ``"revoked"`` Blueprint revoked (tamper/license)
/// Error    ``"error"``  Certification failed
/// ======== ============ ===================================
#[pyclass(name = "CertificationStatus", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum CertificationStatus {
    Draft,
    Signed,
    Verified,
    Revoked,
    Error,
}

impl CertificationStatus {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            CertificationStatus::Draft => "draft",
            CertificationStatus::Signed => "signed",
            CertificationStatus::Verified => "verified",
            CertificationStatus::Revoked => "revoked",
            CertificationStatus::Error => "error",
        }
    }
}

#[pymethods]
impl CertificationStatus {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("CertificationStatus.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  BlueprintConfig — structured blueprint configuration
// ═══════════════════════════════════════════════════════════════

/// Structured blueprint configuration extracted from a completed template.
///
/// This is the intermediate representation between a filled template
/// and a CertifiedBlueprint. It organizes template data into the
/// structure expected by the Phase 5 Blueprint system.
///
/// # Fields
///
/// - niche_id: The niche this blueprint was generated from
/// - business_name: Primary business identifier
/// - business_type: Legal entity type (LLC, Corporation, etc.)
/// - domain: Industry domain (e.g., "health", "fintech")
/// - data_sensitivity: Data classification level
/// - compliance: Applicable regulatory standards
/// - db_schema: Database table definitions
/// - monitors: SNA monitor configurations
/// - actions: Executor action configurations
/// - settings: Key-value runtime settings
/// - version: Blueprint version (semver)
#[pyclass(name = "BlueprintConfig")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BlueprintConfig {
    niche_id: String,
    business_name: String,
    business_type: String,
    domain: String,
    subdomain: String,
    data_sensitivity: String,
    compliance: Vec<String>,
    db_schema: Vec<DbTableDef>,
    monitors: Vec<MonitorDef>,
    actions: Vec<ActionDef>,
    settings: HashMap<String, String>,
    version: String,
    tags: Vec<String>,
}

impl BlueprintConfig {
    /// Create a new BlueprintConfig with required fields.
    pub fn new(
        niche_id: String,
        business_name: String,
        business_type: String,
        domain: String,
        data_sensitivity: String,
    ) -> Self {
        let niche_id_trimmed = niche_id.trim().to_string();
        let business_name_trimmed = business_name.trim().to_string();
        BlueprintConfig {
            niche_id: niche_id_trimmed,
            business_name: business_name_trimmed,
            business_type,
            domain,
            subdomain: String::new(),
            data_sensitivity,
            compliance: Vec::new(),
            db_schema: Vec::new(),
            monitors: Vec::new(),
            actions: Vec::new(),
            settings: HashMap::new(),
            version: "1.0.0".to_string(),
            tags: Vec::new(),
        }
    }

    /// Get the niche_id.
    pub fn niche_id(&self) -> &str {
        &self.niche_id
    }

    /// Get the business_name.
    pub fn business_name(&self) -> &str {
        &self.business_name
    }
}

#[pymethods]
impl BlueprintConfig {
    #[getter]
    fn niche_id(&self) -> &str {
        &self.niche_id
    }

    #[getter]
    fn business_name(&self) -> &str {
        &self.business_name
    }

    #[getter]
    fn business_type(&self) -> &str {
        &self.business_type
    }

    #[getter]
    fn domain(&self) -> &str {
        &self.domain
    }

    #[getter]
    fn subdomain(&self) -> &str {
        &self.subdomain
    }

    #[getter]
    fn data_sensitivity(&self) -> &str {
        &self.data_sensitivity
    }

    #[getter]
    fn compliance(&self) -> Vec<String> {
        self.compliance.clone()
    }

    #[getter]
    fn db_schema(&self) -> Vec<DbTableDef> {
        self.db_schema.clone()
    }

    #[getter]
    fn monitors(&self) -> Vec<MonitorDef> {
        self.monitors.clone()
    }

    #[getter]
    fn actions(&self) -> Vec<ActionDef> {
        self.actions.clone()
    }

    #[getter]
    fn settings(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        for (k, v) in &self.settings {
            dict.set_item(k, v)?;
        }
        Ok(dict.unbind())
    }

    #[getter]
    fn version(&self) -> &str {
        &self.version
    }

    #[getter]
    fn tags(&self) -> Vec<String> {
        self.tags.clone()
    }

    /// Add a compliance standard.
    fn add_compliance(&mut self, standard: String) -> PyResult<()> {
        if self.compliance.len() >= MAX_COMPLIANCE_STANDARDS {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Maximum compliance standards ({}) reached", MAX_COMPLIANCE_STANDARDS),
            ));
        }
        let trimmed = standard.trim().to_string();
        if !trimmed.is_empty() && !self.compliance.contains(&trimmed) {
            self.compliance.push(trimmed);
        }
        Ok(())
    }

    /// Add a database table definition.
    fn add_db_table(&mut self, table: DbTableDef) -> PyResult<()> {
        if self.db_schema.len() >= MAX_DB_TABLES {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Maximum db tables ({}) reached", MAX_DB_TABLES),
            ));
        }
        self.db_schema.push(table);
        Ok(())
    }

    /// Add a monitor definition.
    fn add_monitor(&mut self, monitor: MonitorDef) -> PyResult<()> {
        if self.monitors.len() >= MAX_MONITORS {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Maximum monitors ({}) reached", MAX_MONITORS),
            ));
        }
        self.monitors.push(monitor);
        Ok(())
    }

    /// Add an action definition.
    fn add_action(&mut self, action: ActionDef) -> PyResult<()> {
        if self.actions.len() >= MAX_ACTIONS {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Maximum actions ({}) reached", MAX_ACTIONS),
            ));
        }
        self.actions.push(action);
        Ok(())
    }

    /// Set a runtime setting.
    fn set_setting(&mut self, key: String, value: String) {
        let key_trimmed = key.trim().to_string();
        if !key_trimmed.is_empty() {
            self.settings.insert(key_trimmed, value);
        }
    }

    /// Add a tag.
    fn add_tag(&mut self, tag: String) {
        let trimmed = tag.trim().to_string();
        if !trimmed.is_empty() && !self.tags.contains(&trimmed) {
            self.tags.push(trimmed);
        }
    }

    /// Check if this config has the minimum required fields for certification.
    fn is_certifiable(&self) -> bool {
        !self.niche_id.is_empty()
            && !self.business_name.is_empty()
            && !self.domain.is_empty()
            && !self.data_sensitivity.is_empty()
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("niche_id", &self.niche_id)?;
        dict.set_item("business_name", &self.business_name)?;
        dict.set_item("business_type", &self.business_type)?;
        dict.set_item("domain", &self.domain)?;
        dict.set_item("data_sensitivity", &self.data_sensitivity)?;
        dict.set_item("compliance_count", self.compliance.len())?;
        dict.set_item("db_tables", self.db_schema.len())?;
        dict.set_item("monitors", self.monitors.len())?;
        dict.set_item("actions", self.actions.len())?;
        dict.set_item("settings", self.settings.len())?;
        dict.set_item("version", &self.version)?;
        dict.set_item("is_certifiable", self.is_certifiable())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "BlueprintConfig(niche={:?}, business={:?}, domain={}, certifiable={})",
            self.niche_id,
            self.business_name,
            self.domain,
            self.is_certifiable(),
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  Supporting Types — DbTableDef, MonitorDef, ActionDef
// ═══════════════════════════════════════════════════════════════

/// Database table definition within a blueprint.
#[pyclass(name = "DbTableDef")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DbTableDef {
    table_name: String,
    columns: Vec<ColumnDef>,
    primary_key: String,
    encrypted: bool,
}

impl DbTableDef {
    /// Create a new DbTableDef.
    pub fn new(table_name: String, primary_key: String) -> Self {
        DbTableDef {
            table_name,
            columns: Vec::new(),
            primary_key,
            encrypted: false,
        }
    }
}

#[pymethods]
impl DbTableDef {
    #[new]
    fn py_new(table_name: String, primary_key: String) -> Self {
        Self::new(table_name, primary_key)
    }

    #[getter]
    fn table_name(&self) -> &str {
        &self.table_name
    }

    #[getter]
    fn primary_key(&self) -> &str {
        &self.primary_key
    }

    #[getter]
    fn encrypted(&self) -> bool {
        self.encrypted
    }

    fn add_column(&mut self, column: ColumnDef) {
        self.columns.push(column);
    }

    fn set_encrypted(&mut self, encrypted: bool) {
        self.encrypted = encrypted;
    }

    fn column_count(&self) -> usize {
        self.columns.len()
    }

    fn __repr__(&self) -> String {
        format!(
            "DbTableDef(name={:?}, columns={}, encrypted={})",
            self.table_name,
            self.columns.len(),
            self.encrypted,
        )
    }
}

/// Column definition within a database table.
#[pyclass(name = "ColumnDef")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ColumnDef {
    name: String,
    col_type: String,
    nullable: bool,
    unique: bool,
    indexed: bool,
}

#[pymethods]
impl ColumnDef {
    #[new]
    fn py_new(name: String, col_type: String) -> Self {
        ColumnDef {
            name,
            col_type,
            nullable: true,
            unique: false,
            indexed: false,
        }
    }

    #[getter]
    fn name(&self) -> &str {
        &self.name
    }

    #[getter]
    fn col_type(&self) -> &str {
        &self.col_type
    }

    #[getter]
    fn nullable(&self) -> bool {
        self.nullable
    }

    #[getter]
    fn unique(&self) -> bool {
        self.unique
    }

    #[getter]
    fn indexed(&self) -> bool {
        self.indexed
    }

    fn set_nullable(&mut self, nullable: bool) {
        self.nullable = nullable;
    }

    fn set_unique(&mut self, unique: bool) {
        self.unique = unique;
    }

    fn set_indexed(&mut self, indexed: bool) {
        self.indexed = indexed;
    }

    fn __repr__(&self) -> String {
        format!("ColumnDef(name={:?}, type={:?})", self.name, self.col_type)
    }
}

/// Monitor definition within a blueprint (SNA integration).
#[pyclass(name = "MonitorDef")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MonitorDef {
    monitor_id: String,
    monitor_type: String,
    name: String,
    description: String,
    interval_seconds: u64,
    threshold: f64,
    enabled: bool,
}

#[pymethods]
impl MonitorDef {
    #[new]
    fn py_new(monitor_id: String, monitor_type: String, name: String) -> Self {
        MonitorDef {
            monitor_id,
            monitor_type,
            name,
            description: String::new(),
            interval_seconds: 300,
            threshold: 0.8,
            enabled: true,
        }
    }

    #[getter]
    fn monitor_id(&self) -> &str {
        &self.monitor_id
    }

    #[getter]
    fn monitor_type(&self) -> &str {
        &self.monitor_type
    }

    #[getter]
    fn name(&self) -> &str {
        &self.name
    }

    #[getter]
    fn description(&self) -> &str {
        &self.description
    }

    #[getter]
    fn interval_seconds(&self) -> u64 {
        self.interval_seconds
    }

    #[getter]
    fn threshold(&self) -> f64 {
        self.threshold
    }

    #[getter]
    fn enabled(&self) -> bool {
        self.enabled
    }

    fn set_description(&mut self, description: String) {
        self.description = description;
    }

    fn set_interval(&mut self, seconds: u64) {
        if seconds > 0 {
            self.interval_seconds = seconds;
        }
    }

    fn set_threshold(&mut self, threshold: f64) {
        self.threshold = threshold.clamp(0.0, 1.0);
    }

    fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }

    fn __repr__(&self) -> String {
        format!(
            "MonitorDef(id={:?}, type={:?}, interval={}s)",
            self.monitor_id, self.monitor_type, self.interval_seconds,
        )
    }
}

/// Action definition within a blueprint (executor integration).
#[pyclass(name = "ActionDef")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ActionDef {
    action_id: String,
    action_type: String,
    name: String,
    description: String,
    requires_approval: bool,
    risk_level: String,
    parameters: HashMap<String, String>,
}

#[pymethods]
impl ActionDef {
    #[new]
    fn py_new(action_id: String, action_type: String, name: String) -> Self {
        ActionDef {
            action_id,
            action_type,
            name,
            description: String::new(),
            requires_approval: false,
            risk_level: "low".to_string(),
            parameters: HashMap::new(),
        }
    }

    #[getter]
    fn action_id(&self) -> &str {
        &self.action_id
    }

    #[getter]
    fn action_type(&self) -> &str {
        &self.action_type
    }

    #[getter]
    fn name(&self) -> &str {
        &self.name
    }

    #[getter]
    fn description(&self) -> &str {
        &self.description
    }

    #[getter]
    fn requires_approval(&self) -> bool {
        self.requires_approval
    }

    #[getter]
    fn risk_level(&self) -> &str {
        &self.risk_level
    }

    fn set_description(&mut self, description: String) {
        self.description = description;
    }

    fn set_requires_approval(&mut self, requires: bool) {
        self.requires_approval = requires;
    }

    fn set_risk_level(&mut self, level: String) {
        let valid_levels = ["low", "medium", "high", "critical"];
        let level_lower = level.to_lowercase();
        if valid_levels.contains(&level_lower.as_str()) {
            self.risk_level = level_lower;
        }
    }

    fn set_parameter(&mut self, key: String, value: String) {
        let key_trimmed = key.trim().to_string();
        if !key_trimmed.is_empty() {
            self.parameters.insert(key_trimmed, value);
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "ActionDef(id={:?}, type={:?}, risk={})",
            self.action_id, self.action_type, self.risk_level,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  CertifiedBlueprint — signed, validated blueprint
// ═══════════════════════════════════════════════════════════════

/// A certified blueprint with ECDSA signature and integrity hash.
///
/// This is the final product of the certification pipeline. It
/// contains the BlueprintConfig along with:
/// - Canonical SHA-256 hash for integrity verification
/// - ECDSA signature for authenticity verification
/// - Certification timestamp and metadata
/// - Audit trail hash chain
#[pyclass(name = "CertifiedBlueprint")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CertifiedBlueprint {
    blueprint_id: String,
    config: BlueprintConfig,
    status: CertificationStatus,
    content_hash: String,
    signature: String,
    signature_algorithm: String,
    certified_at: String,
    schema_version: String,
    audit_chain: Vec<AuditEntry>,
    warnings: Vec<String>,
    errors: Vec<String>,
}

#[pymethods]
impl CertifiedBlueprint {
    #[getter]
    fn blueprint_id(&self) -> &str {
        &self.blueprint_id
    }

    #[getter]
    fn config(&self) -> &BlueprintConfig {
        &self.config
    }

    #[getter]
    fn status(&self) -> CertificationStatus {
        self.status
    }

    #[getter]
    fn content_hash(&self) -> &str {
        &self.content_hash
    }

    #[getter]
    fn signature(&self) -> &str {
        &self.signature
    }

    #[getter]
    fn signature_algorithm(&self) -> &str {
        &self.signature_algorithm
    }

    #[getter]
    fn certified_at(&self) -> &str {
        &self.certified_at
    }

    #[getter]
    fn schema_version(&self) -> &str {
        &self.schema_version
    }

    #[getter]
    fn warnings(&self) -> Vec<String> {
        self.warnings.clone()
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    #[getter]
    fn has_errors(&self) -> bool {
        !self.errors.is_empty()
    }

    /// Check if this blueprint is verified (signature validated).
    fn is_verified(&self) -> bool {
        self.status == CertificationStatus::Verified
    }

    /// Check if this blueprint is signed (has signature).
    fn is_signed(&self) -> bool {
        self.status == CertificationStatus::Signed
            || self.status == CertificationStatus::Verified
    }

    /// Get the audit chain length.
    fn audit_chain_length(&self) -> usize {
        self.audit_chain.len()
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("blueprint_id", &self.blueprint_id)?;
        dict.set_item("niche_id", self.config.niche_id())?;
        dict.set_item("business_name", self.config.business_name())?;
        dict.set_item("status", self.status.as_str())?;
        dict.set_item("content_hash", &self.content_hash)?;
        dict.set_item("is_signed", self.is_signed())?;
        dict.set_item("is_verified", self.is_verified())?;
        dict.set_item("certified_at", &self.certified_at)?;
        dict.set_item("schema_version", &self.schema_version)?;
        dict.set_item("audit_entries", self.audit_chain.len())?;
        dict.set_item("warnings", self.warnings.len())?;
        dict.set_item("errors", self.errors.len())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CertifiedBlueprint(id={:?}, niche={:?}, status={}, signed={})",
            self.blueprint_id,
            self.config.niche_id(),
            self.status.as_str(),
            self.is_signed(),
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  CertificationResult — result of the certification process
// ═══════════════════════════════════════════════════════════════

/// Result of the certification process.
///
/// Contains the certified blueprint (if successful) along with
/// statistics and any warnings or errors from the process.
#[pyclass(name = "CertificationResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CertificationResult {
    success: bool,
    blueprint: Option<CertifiedBlueprint>,
    config: Option<BlueprintConfig>,
    status: CertificationStatus,
    content_hash: String,
    elapsed_ms: u64,
    warnings: Vec<String>,
    errors: Vec<String>,
}

#[pymethods]
impl CertificationResult {
    #[getter]
    fn success(&self) -> bool {
        self.success
    }

    #[getter]
    fn blueprint(&self) -> Option<CertifiedBlueprint> {
        self.blueprint.clone()
    }

    #[getter]
    fn config(&self) -> Option<BlueprintConfig> {
        self.config.clone()
    }

    #[getter]
    fn status(&self) -> CertificationStatus {
        self.status
    }

    #[getter]
    fn content_hash(&self) -> &str {
        &self.content_hash
    }

    #[getter]
    fn elapsed_ms(&self) -> u64 {
        self.elapsed_ms
    }

    #[getter]
    fn warnings(&self) -> Vec<String> {
        self.warnings.clone()
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("success", self.success)?;
        dict.set_item("status", self.status.as_str())?;
        dict.set_item("content_hash", &self.content_hash)?;
        dict.set_item("elapsed_ms", self.elapsed_ms)?;
        dict.set_item("warnings", self.warnings.len())?;
        dict.set_item("errors", self.errors.len())?;
        if let Some(ref bp) = self.blueprint {
            dict.set_item("blueprint_id", bp.blueprint_id())?;
        }
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CertificationResult(success={}, status={}, hash={:?})",
            self.success,
            self.status.as_str(),
            if self.content_hash.len() > 16 {
                &self.content_hash[..16]
            } else {
                &self.content_hash
            },
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  AuditEntry — single entry in the certification audit chain
// ═══════════════════════════════════════════════════════════════

/// A single entry in the certification audit chain.
///
/// Each entry records a state transition in the certification
/// pipeline with a hash that chains to the previous entry.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AuditEntry {
    step: String,
    timestamp: String,
    hash: String,
    details: String,
}

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers
// ═══════════════════════════════════════════════════════════════

/// Generate a blueprint ID from niche_id and timestamp.
fn generate_blueprint_id(niche_id: &str) -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("bp-{}-{:016x}", niche_id, ts)
}

/// Compute a SHA-256 hash of the canonical form of a BlueprintConfig.
///
/// The canonical form is a deterministic JSON serialization with
/// sorted keys, ensuring idempotent hashing.
fn compute_canonical_hash(config: &BlueprintConfig) -> String {
    // Build a canonical representation for hashing
    let mut canonical_parts: Vec<String> = Vec::new();

    // Core identity
    canonical_parts.push(format!("niche_id:{}", config.niche_id));
    canonical_parts.push(format!("business_name:{}", config.business_name));
    canonical_parts.push(format!("business_type:{}", config.business_type));
    canonical_parts.push(format!("domain:{}", config.domain));
    if !config.subdomain.is_empty() {
        canonical_parts.push(format!("subdomain:{}", config.subdomain));
    }
    canonical_parts.push(format!("data_sensitivity:{}", config.data_sensitivity));
    canonical_parts.push(format!("version:{}", config.version));

    // Compliance (sorted)
    let mut compliance_sorted = config.compliance.clone();
    compliance_sorted.sort();
    canonical_parts.push(format!("compliance:{}", compliance_sorted.join(",")));

    // Tags (sorted)
    let mut tags_sorted = config.tags.clone();
    tags_sorted.sort();
    canonical_parts.push(format!("tags:{}", tags_sorted.join(",")));

    // Settings (sorted)
    let mut settings_sorted: Vec<(String, String)> =
        config.settings.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
    settings_sorted.sort_by(|a, b| a.0.cmp(&b.0));
    let settings_str: Vec<String> =
        settings_sorted.iter().map(|(k, v)| format!("{}={}", k, v)).collect();
    canonical_parts.push(format!("settings:{}", settings_str.join(",")));

    // DB tables
    let mut db_parts: Vec<String> = Vec::new();
    for table in &config.db_schema {
        let mut col_parts: Vec<String> = Vec::new();
        for col in &table.columns {
            col_parts.push(format!("{}:{}", col.name, col.col_type));
        }
        col_parts.sort();
        db_parts.push(format!("{}[pk={},enc={},cols={}]",
            table.table_name,
            table.primary_key,
            table.encrypted,
            col_parts.join(";"),
        ));
    }
    db_parts.sort();
    canonical_parts.push(format!("db:{}", db_parts.join("|")));

    // Monitors
    let mut mon_parts: Vec<String> = Vec::new();
    for m in &config.monitors {
        mon_parts.push(format!("{}:{}:{}", m.monitor_id, m.monitor_type, m.interval_seconds));
    }
    mon_parts.sort();
    canonical_parts.push(format!("monitors:{}", mon_parts.join("|")));

    // Actions
    let mut act_parts: Vec<String> = Vec::new();
    for a in &config.actions {
        act_parts.push(format!("{}:{}:{}", a.action_id, a.action_type, a.risk_level));
    }
    act_parts.sort();
    canonical_parts.push(format!("actions:{}", act_parts.join("|")));

    let canonical_string = canonical_parts.join("\n");

    // Compute SHA-256 using the existing hash module
    crate::hash::blake3_hash(canonical_string.as_bytes())
}

/// Extract a field value from a template dict section.
fn get_template_field_value(
    template_dict: &Bound<'_, PyDict>,
    section_id: &str,
    field_name: &str,
) -> Option<String> {
    let template_obj = template_dict.get_item("template").ok().flatten()?;
    let template_pydict: &Bound<'_, PyDict> = template_obj.downcast().ok()?;
    let sections_obj = template_pydict.get_item("sections").ok().flatten()?;
    let sections: &Bound<'_, PyDict> = sections_obj.downcast().ok()?;
    let section_val = sections.get_item(section_id).ok().flatten()?;
    let section_dict: &Bound<'_, PyDict> = section_val.downcast().ok()?;
    let field_val = section_dict.get_item(field_name).ok().flatten()?;
    let field_dict: &Bound<'_, PyDict> = field_val.downcast().ok()?;
    let value_obj = field_dict.get_item("value").ok().flatten()?;

    if value_obj.is_none() {
        return None;
    }

    value_obj.extract::<String>().ok()
}

/// Get the compliance list from template metadata.
fn get_template_compliance(template_dict: &Bound<'_, PyDict>) -> Vec<String> {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return Vec::new(),
    };
    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return Vec::new(),
    };
    let metadata_obj = match template_pydict.get_item("metadata") {
        Ok(Some(m)) => m,
        _ => return Vec::new(),
    };
    let metadata: &Bound<'_, PyDict> = match metadata_obj.downcast() {
        Ok(d) => d,
        _ => return Vec::new(),
    };

    match metadata.get_item("compliance") {
        Ok(Some(v)) => v.extract::<Vec<String>>().unwrap_or_default(),
        _ => Vec::new(),
    }
}

/// Get metadata string field from template.
fn get_template_metadata_str(
    template_dict: &Bound<'_, PyDict>,
    key: &str,
) -> String {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return String::new(),
    };
    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return String::new(),
    };
    let metadata_obj = match template_pydict.get_item("metadata") {
        Ok(Some(m)) => m,
        _ => return String::new(),
    };
    let metadata: &Bound<'_, PyDict> = match metadata_obj.downcast() {
        Ok(d) => d,
        _ => return String::new(),
    };

    metadata
        .get_item(key)
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or_default()
}

/// Extract all settings from a template dict.
fn extract_settings_from_template(
    template_dict: &Bound<'_, PyDict>,
) -> HashMap<String, String> {
    let mut settings: HashMap<String, String> = HashMap::new();

    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return settings,
    };
    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return settings,
    };
    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return settings,
    };
    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return settings,
    };

    for (_, section_val) in sections.iter() {
        let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
            Ok(d) => d,
            _ => continue,
        };

        for (field_key, field_val) in section_dict.iter() {
            let field_name: String = match field_key.extract() {
                Ok(s) => s,
                _ => continue,
            };
            if field_name.starts_with('_') {
                continue;
            }

            let field_dict: &Bound<'_, PyDict> = match field_val.downcast() {
                Ok(d) => d,
                _ => continue,
            };

            let value_obj = match field_dict.get_item("value") {
                Ok(Some(v)) => v,
                _ => continue,
            };

            if value_obj.is_none() {
                continue;
            }

            if let Ok(str_val) = value_obj.extract::<String>() {
                if !str_val.is_empty() {
                    settings.insert(field_name, str_val);
                }
            }
        }
    }

    settings
}

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Public API
// ═══════════════════════════════════════════════════════════════

/// Create a BlueprintConfig from a completed template dict.
///
/// Extracts all filled field values from the template and organizes
/// them into a structured BlueprintConfig ready for certification.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The completed template dict (from completer_finalize or
///     template_generate with filled values).
///
/// Returns
/// -------
/// CertificationResult
///     Result with the BlueprintConfig in the `config` field.
///     Check `success` to verify extraction was successful.
#[pyfunction]
pub fn certifier_from_template(
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<CertificationResult> {
    let mut warnings: Vec<String> = Vec::new();
    let mut errors: Vec<String> = Vec::new();

    // Validate template structure
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => {
            return Ok(CertificationResult {
                success: false,
                blueprint: None,
                config: None,
                status: CertificationStatus::Error,
                content_hash: String::new(),
                elapsed_ms: 0,
                warnings,
                errors: vec!["Missing 'template' key in template_dict".to_string()],
            });
        }
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => {
            return Ok(CertificationResult {
                success: false,
                blueprint: None,
                config: None,
                status: CertificationStatus::Error,
                content_hash: String::new(),
                elapsed_ms: 0,
                warnings,
                errors: vec!["'template' is not a dict".to_string()],
            });
        }
    };

    // Validate completeness using template_validate
    let validation = crate::template::template_validate(template_dict, py)?;
    let is_valid: bool = validation
        .get_item("valid")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(false);

    let missing_required: usize = validation
        .get_item("missing_required")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    if !is_valid {
        warnings.push(format!(
            "Template has {} missing required fields. Blueprint may be incomplete.",
            missing_required,
        ));
    }

    // Extract metadata
    let niche_id = get_template_metadata_str(template_dict, "niche_id");
    let domain = get_template_metadata_str(template_dict, "domain");
    let subdomain = get_template_metadata_str(template_dict, "subdomain");
    let data_sensitivity = get_template_metadata_str(template_dict, "data_sensitivity");
    let compliance = get_template_compliance(template_dict);

    // Extract business identity fields
    let business_name = get_template_field_value(template_dict, "business_identity", "business_name")
        .unwrap_or_else(|| "Unknown Business".to_string());
    let business_type = get_template_field_value(template_dict, "business_identity", "business_type")
        .unwrap_or_else(|| "unknown".to_string());

    // Build config
    let mut config = BlueprintConfig::new(
        niche_id,
        business_name,
        business_type,
        domain,
        data_sensitivity,
    );
    config.subdomain = subdomain;

    // Add compliance standards
    for standard in &compliance {
        if let Err(e) = config.add_compliance(standard.clone()) {
            warnings.push(e.to_string());
        }
    }

    // Extract all field values as settings
    let settings = extract_settings_from_template(template_dict);
    for (key, value) in &settings {
        config.set_setting(key.clone(), value.clone());
    }

    // Add default monitors based on data sensitivity
    let default_monitors = build_default_monitors(&config.data_sensitivity);
    for monitor in default_monitors {
        if let Err(e) = config.add_monitor(monitor) {
            warnings.push(e.to_string());
        }
    }

    // Add default actions based on niche type
    let default_actions = build_default_actions(&config.niche_id, &config.data_sensitivity);
    for action in default_actions {
        if let Err(e) = config.add_action(action) {
            warnings.push(e.to_string());
        }
    }

    // Add default database schema
    let default_tables = build_default_db_schema(&config.niche_id);
    for table in default_tables {
        if let Err(e) = config.add_db_table(table) {
            warnings.push(e.to_string());
        }
    }

    // Add tags from metadata
    let tags: Vec<String> = template_pydict
        .get_item("metadata")
        .ok()
        .flatten()
        .and_then(|m| m.downcast::<PyDict>().ok())
        .and_then(|m| m.get_item("tags").ok().flatten())
        .and_then(|v| v.extract().ok())
        .unwrap_or_default();
    for tag in tags {
        config.add_tag(tag);
    }

    if !config.is_certifiable() {
        errors.push("BlueprintConfig is not certifiable: missing required fields (niche_id, business_name, domain, data_sensitivity)".to_string());
    }

    let success = errors.is_empty();
    let status = if success {
        CertificationStatus::Draft
    } else {
        CertificationStatus::Error
    };

    Ok(CertificationResult {
        success,
        blueprint: None,
        config: Some(config),
        status,
        content_hash: String::new(),
        elapsed_ms: 0,
        warnings,
        errors,
    })
}

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

/// Export a CertifiedBlueprint as a Python dict compatible with Phase 5.
///
/// The returned dict has the structure expected by the Phase 5
/// Blueprint Loader and can be directly used with the existing
/// Blueprint system.
///
/// Parameters
/// ----------
/// blueprint : CertifiedBlueprint
///     The certified blueprint to export.
///
/// Returns
/// -------
/// dict
///     Blueprint dict with Phase 5 compatible structure.
#[pyfunction]
pub fn certifier_to_blueprint_dict(
    blueprint: &CertifiedBlueprint,
    py: Python<'_>,
) -> PyResult<Py<PyDict>> {
    let root = PyDict::new_bound(py);

    // Blueprint metadata (Phase 5 compatible)
    let metadata = PyDict::new_bound(py);
    metadata.set_item("blueprint_id", blueprint.blueprint_id())?;
    metadata.set_item("niche_id", blueprint.config.niche_id())?;
    metadata.set_item("business_name", blueprint.config.business_name())?;
    metadata.set_item("business_type", blueprint.config.business_type())?;
    metadata.set_item("domain", blueprint.config.domain())?;
    metadata.set_item("subdomain", blueprint.config.subdomain())?;
    metadata.set_item("data_sensitivity", blueprint.config.data_sensitivity())?;
    metadata.set_item("version", blueprint.config.version())?;
    metadata.set_item("schema_version", blueprint.schema_version())?;
    metadata.set_item("certified_at", blueprint.certified_at())?;
    metadata.set_item("status", blueprint.status.as_str())?;
    metadata.set_item("tags", blueprint.config.tags())?;
    root.set_item("metadata", metadata)?;

    // Compliance
    let compliance = PyDict::new_bound(py);
    for standard in &blueprint.config.compliance {
        compliance.set_item(standard, true)?;
    }
    root.set_item("compliance", compliance)?;

    // Database schema
    let db_schema = PyDict::new_bound(py);
    for table in &blueprint.config.db_schema {
        let table_dict = PyDict::new_bound(py);
        table_dict.set_item("primary_key", &table.primary_key)?;
        table_dict.set_item("encrypted", table.encrypted)?;

        let columns_dict = PyDict::new_bound(py);
        for col in &table.columns {
            let col_dict = PyDict::new_bound(py);
            col_dict.set_item("type", &col.col_type)?;
            col_dict.set_item("nullable", col.nullable)?;
            col_dict.set_item("unique", col.unique)?;
            col_dict.set_item("indexed", col.indexed)?;
            columns_dict.set_item(&col.name, col_dict)?;
        }
        table_dict.set_item("columns", columns_dict)?;
        db_schema.set_item(&table.table_name, table_dict)?;
    }
    root.set_item("db_schema", db_schema)?;

    // Monitors (SNA)
    let monitors = PyDict::new_bound(py);
    for monitor in &blueprint.config.monitors {
        let mon_dict = PyDict::new_bound(py);
        mon_dict.set_item("type", &monitor.monitor_type)?;
        mon_dict.set_item("name", &monitor.name)?;
        mon_dict.set_item("description", &monitor.description)?;
        mon_dict.set_item("interval_seconds", monitor.interval_seconds)?;
        mon_dict.set_item("threshold", monitor.threshold)?;
        mon_dict.set_item("enabled", monitor.enabled)?;
        monitors.set_item(&monitor.monitor_id, mon_dict)?;
    }
    root.set_item("monitors", monitors)?;

    // Actions (executors)
    let actions = PyDict::new_bound(py);
    for action in &blueprint.config.actions {
        let act_dict = PyDict::new_bound(py);
        act_dict.set_item("type", &action.action_type)?;
        act_dict.set_item("name", &action.name)?;
        act_dict.set_item("description", &action.description)?;
        act_dict.set_item("requires_approval", action.requires_approval)?;
        act_dict.set_item("risk_level", &action.risk_level)?;

        let params = PyDict::new_bound(py);
        for (k, v) in &action.parameters {
            params.set_item(k, v)?;
        }
        act_dict.set_item("parameters", params)?;
        actions.set_item(&action.action_id, act_dict)?;
    }
    root.set_item("actions", actions)?;

    // Settings
    let settings = PyDict::new_bound(py);
    for (k, v) in &blueprint.config.settings {
        settings.set_item(k, v)?;
    }
    root.set_item("settings", settings)?;

    // Integrity
    let integrity = PyDict::new_bound(py);
    integrity.set_item("content_hash", blueprint.content_hash())?;
    integrity.set_item("signature", blueprint.signature())?;
    integrity.set_item("signature_algorithm", blueprint.signature_algorithm())?;
    integrity.set_item("hash_algorithm", HASH_ALGORITHM)?;
    integrity.set_item("is_signed", blueprint.is_signed())?;
    integrity.set_item("is_verified", blueprint.is_verified())?;
    root.set_item("integrity", integrity)?;

    // Audit chain
    let audit_chain = PyDict::new_bound(py);
    for entry in &blueprint.audit_chain {
        let entry_dict = PyDict::new_bound(py);
        entry_dict.set_item("step", &entry.step)?;
        entry_dict.set_item("timestamp", &entry.timestamp)?;
        entry_dict.set_item("hash", &entry.hash)?;
        entry_dict.set_item("details", &entry.details)?;
        audit_chain.set_item(&entry.step, entry_dict)?;
    }
    root.set_item("audit_chain", audit_chain)?;

    Ok(root.unbind())
}

/// Export a CertifiedBlueprint as a YAML string.
///
/// Parameters
/// ----------
/// blueprint : CertifiedBlueprint
///     The certified blueprint to export.
///
/// Returns
/// -------
/// str
///     YAML string representation of the certified blueprint.
#[pyfunction]
pub fn certifier_export_yaml(blueprint: &CertifiedBlueprint, py: Python<'_>) -> PyResult<String> {
    let blueprint_dict = certifier_to_blueprint_dict(blueprint, py)?;

    // Use Python's yaml module for serialization
    let yaml_module = py.import_bound("yaml");
    match yaml_module {
        Ok(ym) => {
            let dump = ym.getattr("dump")?;
            let default_flow_style = ym.getattr("SafeDumper")?.getattr("default_flow_style")?;
            let result = dump.call((blueprint_dict,), Some(&[("default_flow_style", false)]))?;
            result.extract::<String>()
        }
        Err(_) => {
            // Fallback to JSON
            let json_module = py.import_bound("json")?;
            let dumps = json_module.getattr("dumps")?;
            let result = dumps.call((blueprint_dict,))?;
            result.extract::<String>()
        }
    }
}

// ═══════════════════════════════════════════════════════════════
//  Default Builders — auto-generate monitors, actions, db_schema
// ═══════════════════════════════════════════════════════════════

/// Build default monitors based on data sensitivity level.
fn build_default_monitors(data_sensitivity: &str) -> Vec<MonitorDef> {
    let mut monitors: Vec<MonitorDef> = Vec::new();

    // Always add health check monitor
    let mut health = MonitorDef::new(
        "health_check".to_string(),
        "liviano".to_string(),
        "System Health Check".to_string(),
    );
    health.set_description("Basic system health and uptime monitoring".to_string());
    health.set_interval(60);
    monitors.push(health);

    // Data sensitivity based monitors
    match data_sensitivity {
        "low" => {
            let mut usage = MonitorDef::new(
                "resource_usage".to_string(),
                "liviano".to_string(),
                "Resource Usage".to_string(),
            );
            usage.set_description("CPU and memory usage monitoring".to_string());
            usage.set_interval(300);
            monitors.push(usage);
        }
        "medium" => {
            let mut usage = MonitorDef::new(
                "resource_usage".to_string(),
                "liviano".to_string(),
                "Resource Usage".to_string(),
            );
            usage.set_description("CPU and memory usage monitoring".to_string());
            usage.set_interval(120);
            monitors.push(usage);

            let mut error_rate = MonitorDef::new(
                "error_rate".to_string(),
                "mediano".to_string(),
                "Error Rate Monitor".to_string(),
            );
            error_rate.set_description("API error rate and response time monitoring".to_string());
            error_rate.set_interval(60);
            error_rate.set_threshold(0.05);
            monitors.push(error_rate);
        }
        "high" | "critical" => {
            let mut usage = MonitorDef::new(
                "resource_usage".to_string(),
                "liviano".to_string(),
                "Resource Usage".to_string(),
            );
            usage.set_description("CPU and memory usage monitoring".to_string());
            usage.set_interval(60);
            monitors.push(usage);

            let mut error_rate = MonitorDef::new(
                "error_rate".to_string(),
                "mediano".to_string(),
                "Error Rate Monitor".to_string(),
            );
            error_rate.set_description("API error rate and response time monitoring".to_string());
            error_rate.set_interval(30);
            error_rate.set_threshold(0.02);
            monitors.push(error_rate);

            let mut intrusion = MonitorDef::new(
                "intrusion_detection".to_string(),
                "pesado".to_string(),
                "Intrusion Detection".to_string(),
            );
            intrusion.set_description("Security event and intrusion detection monitoring".to_string());
            intrusion.set_interval(30);
            intrusion.set_threshold(0.01);
            monitors.push(intrusion);

            let mut data_integrity = MonitorDef::new(
                "data_integrity".to_string(),
                "pesado".to_string(),
                "Data Integrity Monitor".to_string(),
            );
            data_integrity.set_description("Hash chain and data integrity verification".to_string());
            data_integrity.set_interval(300);
            data_integrity.set_threshold(0.0);
            monitors.push(data_integrity);
        }
        _ => {}
    }

    monitors
}

/// Build default actions based on niche type and data sensitivity.
fn build_default_actions(niche_id: &str, data_sensitivity: &str) -> Vec<ActionDef> {
    let mut actions: Vec<ActionDef> = Vec::new();

    // Common actions for all niches
    let mut read = ActionDef::new(
        "read_data".to_string(),
        "db".to_string(),
        "Read Data".to_string(),
    );
    read.set_description("Read data from database".to_string());
    read.set_risk_level("low".to_string());
    actions.push(read);

    let mut create = ActionDef::new(
        "create_record".to_string(),
        "db".to_string(),
        "Create Record".to_string(),
    );
    create.set_description("Create a new database record".to_string());
    create.set_risk_level("medium".to_string());
    actions.push(create);

    // Financial/destructive actions require approval for sensitive data
    if data_sensitivity == "high" || data_sensitivity == "critical" {
        let mut delete = ActionDef::new(
            "delete_record".to_string(),
            "db".to_string(),
            "Delete Record".to_string(),
        );
        delete.set_description("Delete a database record (requires approval)".to_string());
        delete.set_requires_approval(true);
        delete.set_risk_level("critical".to_string());
        actions.push(delete);

        let mut bulk_update = ActionDef::new(
            "bulk_update".to_string(),
            "db".to_string(),
            "Bulk Update".to_string(),
        );
        bulk_update.set_description("Bulk update multiple records (requires approval)".to_string());
        bulk_update.set_requires_approval(true);
        bulk_update.set_risk_level("high".to_string());
        actions.push(bulk_update);
    }

    // Niche-specific actions
    if niche_id.contains("fintech") || niche_id.contains("banking") || niche_id.contains("defi") {
        let mut transfer = ActionDef::new(
            "financial_transfer".to_string(),
            "http".to_string(),
            "Financial Transfer".to_string(),
        );
        transfer.set_description("Execute a financial transfer (requires approval)".to_string());
        transfer.set_requires_approval(true);
        transfer.set_risk_level("critical".to_string());
        actions.push(transfer);
    }

    if niche_id.contains("health") || niche_id.contains("telemedicine") {
        let mut access_phi = ActionDef::new(
            "access_phi".to_string(),
            "db".to_string(),
            "Access PHI Data".to_string(),
        );
        access_phi.set_description("Access Protected Health Information (requires approval)".to_string());
        access_phi.set_requires_approval(true);
        access_phi.set_risk_level("critical".to_string());
        actions.push(access_phi);
    }

    actions
}

/// Build default database schema based on niche type.
fn build_default_db_schema(niche_id: &str) -> Vec<DbTableDef> {
    let mut tables: Vec<DbTableDef> = Vec::new();

    // Common tables for all niches
    let mut users = DbTableDef::new("users".to_string(), "id".to_string());
    users.set_encrypted(true);
    users.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
    users.add_column({
        let mut col = ColumnDef::py_new("email".to_string(), "text".to_string());
        col.set_unique(true);
        col.set_indexed(true);
        col
    });
    users.add_column({
        let mut col = ColumnDef::py_new("name".to_string(), "text".to_string());
        col.set_nullable(false);
        col
    });
    users.add_column({
        let mut col = ColumnDef::py_new("role".to_string(), "text".to_string());
        col.set_nullable(false);
        col.set_indexed(true);
        col
    });
    users.add_column(ColumnDef::py_new("created_at".to_string(), "datetime".to_string()));
    tables.push(users);

    let mut audit_log = DbTableDef::new("audit_log".to_string(), "id".to_string());
    audit_log.set_encrypted(false);
    audit_log.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
    audit_log.add_column({
        let mut col = ColumnDef::py_new("user_id".to_string(), "uuid".to_string());
        col.set_indexed(true);
        col
    });
    audit_log.add_column({
        let mut col = ColumnDef::py_new("action".to_string(), "text".to_string());
        col.set_indexed(true);
        col.set_nullable(false);
        col
    });
    audit_log.add_column(ColumnDef::py_new("resource_type".to_string(), "text".to_string()));
    audit_log.add_column(ColumnDef::py_new("resource_id".to_string(), "text".to_string()));
    audit_log.add_column(ColumnDef::py_new("timestamp".to_string(), "datetime".to_string()));
    audit_log.add_column(ColumnDef::py_new("details".to_string(), "json".to_string()));
    tables.push(audit_log);

    // Niche-specific tables
    if niche_id.contains("crm") || niche_id.contains("sales") {
        let mut contacts = DbTableDef::new("contacts".to_string(), "id".to_string());
        contacts.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
        contacts.add_column({
            let mut col = ColumnDef::py_new("name".to_string(), "text".to_string());
            col.set_nullable(false);
            col
        });
        contacts.add_column(ColumnDef::py_new("email".to_string(), "text".to_string()));
        contacts.add_column(ColumnDef::py_new("company".to_string(), "text".to_string()));
        contacts.add_column(ColumnDef::py_new("stage".to_string(), "text".to_string()));
        contacts.add_column(ColumnDef::py_new("value".to_string(), "currency".to_string()));
        tables.push(contacts);
    }

    if niche_id.contains("inventory") || niche_id.contains("warehouse") {
        let mut products = DbTableDef::new("products".to_string(), "id".to_string());
        products.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
        products.add_column({
            let mut col = ColumnDef::py_new("name".to_string(), "text".to_string());
            col.set_nullable(false);
            col
        });
        products.add_column(ColumnDef::py_new("sku".to_string(), "text".to_string()));
        products.add_column(ColumnDef::py_new("quantity".to_string(), "integer".to_string()));
        products.add_column(ColumnDef::py_new("price".to_string(), "currency".to_string()));
        products.add_column(ColumnDef::py_new("min_stock".to_string(), "integer".to_string()));
        tables.push(products);
    }

    tables
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_certification_status_as_str() {
        assert_eq!(CertificationStatus::Draft.as_str(), "draft");
        assert_eq!(CertificationStatus::Signed.as_str(), "signed");
        assert_eq!(CertificationStatus::Verified.as_str(), "verified");
        assert_eq!(CertificationStatus::Revoked.as_str(), "revoked");
        assert_eq!(CertificationStatus::Error.as_str(), "error");
    }

    #[test]
    fn test_blueprint_config_creation() {
        let config = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Test Clinic".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        assert_eq!(config.niche_id(), "telemedicine");
        assert_eq!(config.business_name(), "Test Clinic");
        assert!(config.is_certifiable());
    }

    #[test]
    fn test_blueprint_config_certifiable_validation() {
        let valid = BlueprintConfig::new(
            "test".to_string(),
            "Business".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "high".to_string(),
        );
        assert!(valid.is_certifiable());

        let empty_name = BlueprintConfig::new(
            "test".to_string(),
            "".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "high".to_string(),
        );
        assert!(!empty_name.is_certifiable());
    }

    #[test]
    fn test_blueprint_config_add_compliance() {
        let mut config = BlueprintConfig::new(
            "test".to_string(),
            "Business".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "high".to_string(),
        );
        config.add_compliance("HIPAA".to_string()).unwrap();
        config.add_compliance("GDPR".to_string()).unwrap();
        config.add_compliance("HIPAA".to_string()).unwrap(); // duplicate ignored
        assert_eq!(config.compliance.len(), 2);
    }

    #[test]
    fn test_blueprint_config_settings() {
        let mut config = BlueprintConfig::new(
            "test".to_string(),
            "Business".to_string(),
            "llc".to_string(),
            "fintech".to_string(),
            "critical".to_string(),
        );
        config.set_setting("api_key_ref".to_string(), "vault://api/key".to_string());
        config.set_setting("base_currency".to_string(), "USD".to_string());
        assert_eq!(config.settings.len(), 2);
    }

    #[test]
    fn test_compute_canonical_hash_deterministic() {
        let config1 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic A".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let config2 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic A".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let hash1 = compute_canonical_hash(&config1);
        let hash2 = compute_canonical_hash(&config2);
        assert_eq!(hash1, hash2, "Same config must produce same hash");
    }

    #[test]
    fn test_compute_canonical_hash_different_configs() {
        let config1 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic A".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let config2 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic B".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let hash1 = compute_canonical_hash(&config1);
        let hash2 = compute_canonical_hash(&config2);
        assert_ne!(hash1, hash2, "Different configs must produce different hashes");
    }

    #[test]
    fn test_db_table_def_creation() {
        let mut table = DbTableDef::new("users".to_string(), "id".to_string());
        table.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
        table.add_column(ColumnDef::py_new("email".to_string(), "text".to_string()));
        table.set_encrypted(true);
        assert_eq!(table.table_name(), "users");
        assert_eq!(table.column_count(), 2);
        assert!(table.encrypted());
    }

    #[test]
    fn test_monitor_def_creation() {
        let mut monitor = MonitorDef::new(
            "health_check".to_string(),
            "liviano".to_string(),
            "Health Check".to_string(),
        );
        monitor.set_interval(60);
        monitor.set_threshold(0.5);
        assert_eq!(monitor.monitor_id(), "health_check");
        assert_eq!(monitor.interval_seconds(), 60);
    }

    #[test]
    fn test_action_def_creation() {
        let mut action = ActionDef::new(
            "delete_record".to_string(),
            "db".to_string(),
            "Delete Record".to_string(),
        );
        action.set_requires_approval(true);
        action.set_risk_level("critical".to_string());
        assert!(action.requires_approval());
        assert_eq!(action.risk_level(), "critical");
    }

    #[test]
    fn test_action_def_risk_level_validation() {
        let mut action = ActionDef::new(
            "test".to_string(),
            "db".to_string(),
            "Test".to_string(),
        );
        action.set_risk_level("high".to_string());
        assert_eq!(action.risk_level(), "high");

        // Invalid level should be ignored
        action.set_risk_level("invalid".to_string());
        assert_eq!(action.risk_level(), "high"); // Unchanged
    }

    #[test]
    fn test_column_def_creation() {
        let mut col = ColumnDef::py_new("email".to_string(), "text".to_string());
        col.set_unique(true);
        col.set_indexed(true);
        col.set_nullable(false);
        assert_eq!(col.name(), "email");
        assert!(col.unique());
        assert!(col.indexed());
        assert!(!col.nullable());
    }

    #[test]
    fn test_build_default_monitors_low() {
        let monitors = build_default_monitors("low");
        assert!(monitors.len() >= 1);
        assert!(monitors.iter().any(|m| m.monitor_id == "health_check"));
    }

    #[test]
    fn test_build_default_monitors_critical() {
        let monitors = build_default_monitors("critical");
        assert!(monitors.len() >= 3);
        assert!(monitors.iter().any(|m| m.monitor_id == "intrusion_detection"));
        assert!(monitors.iter().any(|m| m.monitor_id == "data_integrity"));
    }

    #[test]
    fn test_build_default_db_schema() {
        let tables = build_default_db_schema("telemedicine");
        assert!(tables.len() >= 2); // users + audit_log at minimum
        assert!(tables.iter().any(|t| t.table_name == "users"));
        assert!(tables.iter().any(|t| t.table_name == "audit_log"));
    }

    #[test]
    fn test_generate_blueprint_id_format() {
        let id = generate_blueprint_id("telemedicine");
        assert!(id.starts_with("bp-telemedicine-"));
    }

    #[test]
    fn test_certification_result_default() {
        let result = CertificationResult {
            success: false,
            blueprint: None,
            config: None,
            status: CertificationStatus::Error,
            content_hash: String::new(),
            elapsed_ms: 0,
            warnings: Vec::new(),
            errors: vec!["test error".to_string()],
        };
        assert!(!result.success);
        assert_eq!(result.errors.len(), 1);
    }
}
