use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::blueprint::*;
use super::schema_types::*;
use super::types::*;

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Export to dict / YAML
// ═══════════════════════════════════════════════════════════════

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
    metadata.set_item("business_type", &blueprint.config.business_type)?;
    metadata.set_item("domain", &blueprint.config.domain)?;
    metadata.set_item("subdomain", &blueprint.config.subdomain)?;
    metadata.set_item("data_sensitivity", &blueprint.config.data_sensitivity)?;
    metadata.set_item("version", &blueprint.config.version)?;
    metadata.set_item("schema_version", blueprint.schema_version())?;
    metadata.set_item("certified_at", blueprint.certified_at())?;
    metadata.set_item("status", blueprint.status.as_str())?;
    metadata.set_item("tags", &blueprint.config.tags)?;
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
