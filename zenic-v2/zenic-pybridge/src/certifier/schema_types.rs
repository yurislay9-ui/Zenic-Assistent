use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════
//  Supporting Types — DbTableDef, ColumnDef, MonitorDef, ActionDef
// ═══════════════════════════════════════════════════════════════

/// Database table definition within a blueprint.
#[pyclass(name = "DbTableDef")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DbTableDef {
    pub(super) table_name: String,
    pub(super) columns: Vec<ColumnDef>,
    pub(super) primary_key: String,
    pub(super) encrypted: bool,
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

    pub fn add_column(&mut self, column: ColumnDef) {
        self.columns.push(column);
    }

    pub fn set_encrypted(&mut self, encrypted: bool) {
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
    pub(super) name: String,
    pub(super) col_type: String,
    pub(super) nullable: bool,
    pub(super) unique: bool,
    pub(super) indexed: bool,
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

    pub fn set_nullable(&mut self, nullable: bool) {
        self.nullable = nullable;
    }

    pub fn set_unique(&mut self, unique: bool) {
        self.unique = unique;
    }

    pub fn set_indexed(&mut self, indexed: bool) {
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
    pub(super) monitor_id: String,
    pub(super) monitor_type: String,
    pub(super) name: String,
    pub(super) description: String,
    pub(super) interval_seconds: u64,
    pub(super) threshold: f64,
    pub(super) enabled: bool,
}

impl MonitorDef {
    /// Create a new MonitorDef.
    pub fn new(monitor_id: String, monitor_type: String, name: String) -> Self {
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
}

#[pymethods]
impl MonitorDef {
    #[new]
    fn py_new(monitor_id: String, monitor_type: String, name: String) -> Self {
        Self::new(monitor_id, monitor_type, name)
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

    pub fn set_description(&mut self, description: String) {
        self.description = description;
    }

    pub fn set_interval(&mut self, seconds: u64) {
        if seconds > 0 {
            self.interval_seconds = seconds;
        }
    }

    pub fn set_threshold(&mut self, threshold: f64) {
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
    pub(super) action_id: String,
    pub(super) action_type: String,
    pub(super) name: String,
    pub(super) description: String,
    pub(super) requires_approval: bool,
    pub(super) risk_level: String,
    pub(super) parameters: HashMap<String, String>,
}

impl ActionDef {
    /// Create a new ActionDef.
    pub fn new(action_id: String, action_type: String, name: String) -> Self {
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
}

#[pymethods]
impl ActionDef {
    #[new]
    fn py_new(action_id: String, action_type: String, name: String) -> Self {
        Self::new(action_id, action_type, name)
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

    pub fn set_description(&mut self, description: String) {
        self.description = description;
    }

    pub fn set_requires_approval(&mut self, requires: bool) {
        self.requires_approval = requires;
    }

    pub fn set_risk_level(&mut self, level: String) {
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
