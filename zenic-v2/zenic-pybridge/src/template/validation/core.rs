//! Template validation, missing fields, and field setting functions.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::niche::NicheDefinition;

/// Validate a template dict for completeness.
///
/// Checks all fields in all sections and counts:
/// - How many fields have a non-null, non-empty value
/// - How many required fields are still missing
/// - Overall completion percentage
#[pyfunction]
pub fn template_validate(template_dict: &Bound<'_, PyDict>, py: Python<'_>) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => {
            result.set_item("valid", false)?;
            result.set_item("error", "Missing 'template' key")?;
            return Ok(result.unbind());
        }
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => {
            result.set_item("valid", false)?;
            result.set_item("error", "'template' is not a dict")?;
            return Ok(result.unbind());
        }
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => {
            result.set_item("valid", false)?;
            result.set_item("error", "Missing 'sections' key")?;
            return Ok(result.unbind());
        }
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => {
            result.set_item("valid", false)?;
            result.set_item("error", "'sections' is not a dict")?;
            return Ok(result.unbind());
        }
    };

    let mut total_fields: usize = 0;
    let mut filled_fields: usize = 0;
    let mut missing_required: usize = 0;
    let mut missing_field_names: Vec<String> = Vec::new();

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

            let is_required: bool = field_dict
                .get_item("_required")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or(false);

            let value = field_dict.get_item("value").ok().flatten();
            let has_value = value.as_ref().map_or(false, |v| !v.is_none());

            total_fields += 1;

            if has_value {
                filled_fields += 1;
            } else if is_required {
                missing_required += 1;
                missing_field_names.push(field_name);
            }
        }
    }

    let completion_pct = if total_fields > 0 {
        (filled_fields as f64 / total_fields as f64) * 100.0
    } else {
        100.0
    };

    let status = if missing_required == 0 {
        "complete"
    } else if filled_fields > 0 {
        "partial"
    } else {
        "incomplete"
    };

    let valid = missing_required == 0;

    result.set_item("valid", valid)?;
    result.set_item("total_fields", total_fields)?;
    result.set_item("filled_fields", filled_fields)?;
    result.set_item("missing_required", missing_required)?;
    result.set_item("completion_pct", completion_pct)?;
    result.set_item("status", status)?;
    result.set_item("missing_field_names", missing_field_names)?;

    Ok(result.unbind())
}

/// List all missing required fields in a template.
#[pyfunction]
pub fn template_missing_fields(template_dict: &Bound<'_, PyDict>, py: Python<'_>) -> PyResult<Vec<Py<PyDict>>> {
    let mut results: Vec<Py<PyDict>> = Vec::new();

    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return Ok(results),
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(results),
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return Ok(results),
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(results),
    };

    for (section_key, section_val) in sections.iter() {
        let section_id: String = match section_key.extract() {
            Ok(s) => s,
            _ => continue,
        };

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

            let is_required: bool = field_dict
                .get_item("_required")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or(false);

            if !is_required {
                continue;
            }

            let value = field_dict.get_item("value").ok().flatten();
            let has_value = value.as_ref().map_or(false, |v| !v.is_none());

            if has_value {
                continue;
            }

            let info = PyDict::new_bound(py);
            info.set_item("name", &field_name)?;

            let display_name: String = field_dict
                .get_item("_display")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or_else(|| field_name.clone());
            info.set_item("display_name", display_name)?;

            let field_type: String = field_dict
                .get_item("_type")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or_else(|| "text".into());
            info.set_item("type", field_type)?;

            info.set_item("section", &section_id)?;

            let description: String = field_dict
                .get_item("_description")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or_default();
            info.set_item("description", description)?;

            let condition: String = field_dict
                .get_item("_condition")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or_default();
            if !condition.is_empty() {
                info.set_item("condition", condition)?;
            }

            let enum_variants: Vec<String> = field_dict
                .get_item("_enum_variants")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or_default();
            if !enum_variants.is_empty() {
                info.set_item("enum_variants", enum_variants)?;
            }

            results.push(info.unbind());
        }
    }

    Ok(results)
}

/// Fill a field value in a template dict.
#[pyfunction]
#[pyo3(signature = (template_dict, section_id, field_name, value))]
pub fn template_set_field(
    template_dict: &Bound<'_, PyDict>,
    section_id: &str,
    field_name: &str,
    value: Bound<'_, PyAny>,
) -> PyResult<bool> {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return Ok(false),
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return Ok(false),
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    let section_val = match sections.get_item(section_id) {
        Ok(Some(v)) => v,
        _ => return Ok(false),
    };

    let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    let field_val = match section_dict.get_item(field_name) {
        Ok(Some(v)) => v,
        _ => return Ok(false),
    };

    let field_dict: &Bound<'_, PyDict> = match field_val.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    field_dict.set_item("value", value)?;

    // Recalculate completeness
    let validation = template_validate(template_dict, template_dict.py())?;
    if let Some(completeness) = template_pydict.get_item("completeness").ok().flatten() {
        if let Ok(comp_dict) = completeness.downcast::<PyDict>() {
            if let Some(filled) = validation.get_item("filled_fields").ok().flatten() {
                comp_dict.set_item("filled_fields", filled)?;
            }
            if let Some(missing) = validation.get_item("missing_required").ok().flatten() {
                comp_dict.set_item("missing_required", missing)?;
            }
            if let Some(pct) = validation.get_item("completion_pct").ok().flatten() {
                comp_dict.set_item("completion_pct", pct)?;
            }
            if let Some(status_val) = validation.get_item("status").ok().flatten() {
                comp_dict.set_item("status", &status_val)?;
                // Also update the top-level metadata status
                if let Some(meta) = template_pydict.get_item("metadata").ok().flatten() {
                    if let Ok(meta_dict) = meta.downcast::<PyDict>() {
                        meta_dict.set_item("status", &status_val)?;
                    }
                }
            }
        }
    }

    Ok(true)
}
