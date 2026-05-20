use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use super::schema_types::*;
use super::types::*;

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
    pub(super) niche_id: String,
    pub(super) business_name: String,
    pub(super) business_type: String,
    pub(super) domain: String,
    pub(super) subdomain: String,
    pub(super) data_sensitivity: String,
    pub(super) compliance: Vec<String>,
    pub(super) db_schema: Vec<DbTableDef>,
    pub(super) monitors: Vec<MonitorDef>,
    pub(super) actions: Vec<ActionDef>,
    pub(super) settings: HashMap<String, String>,
    pub(super) version: String,
    pub(super) tags: Vec<String>,
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
    pub fn add_compliance(&mut self, standard: String) -> PyResult<()> {
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
    pub fn add_db_table(&mut self, table: DbTableDef) -> PyResult<()> {
        if self.db_schema.len() >= MAX_DB_TABLES {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Maximum db tables ({}) reached", MAX_DB_TABLES),
            ));
        }
        self.db_schema.push(table);
        Ok(())
    }

    /// Add a monitor definition.
    pub fn add_monitor(&mut self, monitor: MonitorDef) -> PyResult<()> {
        if self.monitors.len() >= MAX_MONITORS {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Maximum monitors ({}) reached", MAX_MONITORS),
            ));
        }
        self.monitors.push(monitor);
        Ok(())
    }

    /// Add an action definition.
    pub fn add_action(&mut self, action: ActionDef) -> PyResult<()> {
        if self.actions.len() >= MAX_ACTIONS {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Maximum actions ({}) reached", MAX_ACTIONS),
            ));
        }
        self.actions.push(action);
        Ok(())
    }

    /// Set a runtime setting.
    pub fn set_setting(&mut self, key: String, value: String) {
        let key_trimmed = key.trim().to_string();
        if !key_trimmed.is_empty() {
            self.settings.insert(key_trimmed, value);
        }
    }

    /// Add a tag.
    pub fn add_tag(&mut self, tag: String) {
        let trimmed = tag.trim().to_string();
        if !trimmed.is_empty() && !self.tags.contains(&trimmed) {
            self.tags.push(trimmed);
        }
    }

    /// Check if this config has the minimum required fields for certification.
    pub fn is_certifiable(&self) -> bool {
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
