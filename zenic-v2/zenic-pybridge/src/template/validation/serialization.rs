//! Template to YAML serialization.

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Serialize a template dict to a YAML string.
///
/// Uses Python's yaml module for serialization. If yaml is not
/// available, falls back to JSON serialization.
#[pyfunction]
pub fn template_to_yaml(template_dict: &Bound<'_, PyDict>, py: Python<'_>) -> PyResult<String> {
    // Try to use Python's yaml module for proper serialization
    let yaml_module = py.import_bound("yaml");
    match yaml_module {
        Ok(ym) => {
            let dump = ym.getattr("dump")?;
            let result = dump.call1((template_dict,))?;
            result.extract::<String>()
        }
        Err(_) => {
            // Fallback to JSON
            let json_module = py.import_bound("json")?;
            let dumps = json_module.getattr("dumps")?;
            let result = dumps.call1((template_dict,))?;
            result.extract::<String>()
        }
    }
}
