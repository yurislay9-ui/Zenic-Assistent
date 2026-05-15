//! YAML Template Schema & Generation for Zenic-Agents.
//!
//! This module implements the dynamic YAML template system:
//! - Generate a YAML template skeleton from a NicheDefinition
//! - Validate a filled template for completeness
//! - List missing required fields (used by interactive agent)
//! - Serialize templates to YAML strings
//!
//! # Template Structure
//!
//! A generated YAML template has this structure:
//!
//! ```yaml
//! template:
//!   metadata:
//!     niche_id: "telemedicine"
//!     niche_name: "Telemedicina"
//!     version: "1.0.0"
//!     generated_at: "2025-01-15T10:30:00Z"
//!     status: "incomplete"
//!   sections:
//!     business_identity:
//!       _title: "Business Identity"
//!       _description: "Core business identification and branding."
//!       business_name:
//!         _type: text
//!         _display: "Business Name"
//!         _required: true
//!         value: null
//!       ...
//!   completeness:
//!     total_fields: 45
//!     filled_fields: 0
//!     missing_required: 30
//!     completion_pct: 0.0
//! ```
//!
//! # PyO3 Functions
//!
//! - `template_generate(niche_id)` — generate skeleton from catalog
//! - `template_validate(template_dict)` — validate completeness
//! - `template_missing_fields(template_dict)` — list missing required fields
//! - `template_to_yaml(template_dict)` — serialize to YAML string

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::catalog::catalog_get_by_id;
use crate::niche::{
    FieldRequirement, NicheDefinition, TemplateFieldType,
};

// ═══════════════════════════════════════════════════════════════
//  Template Generation
// ═══════════════════════════════════════════════════════════════

/// Generate a YAML template skeleton from a niche_id.
///
/// This is the core function of the dynamic template system.
/// It takes a niche_id, looks up the NicheDefinition in the
/// compiled catalog, and generates a Python dict representing
/// the YAML template with all fields set to null.
///
/// Parameters
/// ----------
/// niche_id : str
///     The niche identifier from the catalog.
///
/// Returns
/// -------
/// dict or None
///     The template dict if niche found, None otherwise.
///
/// The returned dict has this structure::
///
///     {
///         "template": {
///             "metadata": { ... },
///             "sections": { ... },
///             "completeness": { ... }
///         }
///     }
#[pyfunction]
pub fn template_generate(niche_id: &str, py: Python<'_>) -> Option<Py<PyDict>> {
    let niche = catalog_get_by_id(niche_id)?;
    Some(generate_template_dict(&niche, py))
}

/// Generate a template from an existing NicheDefinition.
#[pyfunction]
pub fn template_generate_from_niche(niche: &NicheDefinition, py: Python<'_>) -> PyResult<Py<PyDict>> {
    Ok(generate_template_dict(niche, py))
}

/// Internal: build the template dict from a NicheDefinition.
fn generate_template_dict(niche: &NicheDefinition, py: Python<'_>) -> Py<PyDict> {
    let root = PyDict::new_bound(py);
    let template = PyDict::new_bound(py);

    // ── Metadata ────────────────────────────────────────────
    let metadata = PyDict::new_bound(py);
    metadata.set_item("niche_id", niche.niche_id()).unwrap();
    metadata.set_item("niche_name", niche.name()).unwrap();
    metadata.set_item("version", niche.version()).unwrap();
    metadata.set_item("domain", niche.domain()).unwrap();
    metadata.set_item("subdomain", niche.subdomain()).unwrap();
    metadata.set_item("category", niche.category().as_str()).unwrap();
    metadata.set_item("data_sensitivity", niche.data_sensitivity().as_str()).unwrap();
    metadata.set_item("scale", niche.scale()).unwrap();
    metadata.set_item("compliance", niche.compliance()).unwrap();
    metadata.set_item("required_documents", niche.required_documents()).unwrap();
    metadata.set_item("tags", niche.tags()).unwrap();
    metadata.set_item("status", "incomplete").unwrap();

    let now = chrono::Utc::now().to_rfc3339();
    metadata.set_item("generated_at", now.as_str()).unwrap();

    template.set_item("metadata", metadata).unwrap();

    // ── Sections ────────────────────────────────────────────
    let sections = PyDict::new_bound(py);
    let mut total_fields: usize = 0;

    for section in niche.template_sections() {
        let section_dict = PyDict::new_bound(py);
        section_dict.set_item("_title", &section.title).unwrap();
        section_dict.set_item("_description", &section.description).unwrap();
        section_dict.set_item("_order", section.order).unwrap();

        for field in section.fields() {
            let field_dict = PyDict::new_bound(py);
            field_dict.set_item("_type", field.field_type().as_str()).unwrap();
            field_dict.set_item("_display", field.display_name()).unwrap();
            field_dict.set_item("_required", field.is_required()).unwrap();
            field_dict.set_item("_requirement", field.requirement().as_str()).unwrap();

            if !field.description().is_empty() {
                field_dict.set_item("_description", field.description()).unwrap();
            }

            if !field.condition().is_empty() {
                field_dict.set_item("_condition", field.condition()).unwrap();
            }

            // Set value: default if present, null otherwise
            match field.default_value() {
                Some(val) => field_dict.set_item("value", val).unwrap(),
                None => field_dict.set_item("value", py.None()).unwrap(),
            }

            // Type-specific metadata
            if field.field_type() == TemplateFieldType::Enum && !field.enum_variants().is_empty() {
                field_dict.set_item("_enum_variants", field.enum_variants()).unwrap();
            }
            if field.field_type() == TemplateFieldType::Reference && !field.reference_entity().is_empty() {
                field_dict.set_item("_reference_entity", field.reference_entity()).unwrap();
            }
            if field.field_type() == TemplateFieldType::File && !field.file_accept().is_empty() {
                field_dict.set_item("_file_accept", field.file_accept()).unwrap();
            }

            section_dict.set_item(field.name(), field_dict).unwrap();
            total_fields += 1;
        }

        sections.set_item(section.section_id(), section_dict).unwrap();
    }

    template.set_item("sections", sections).unwrap();

    // ── Completeness ────────────────────────────────────────
    let completeness = PyDict::new_bound(py);
    let required_count = niche.required_field_count();
    completeness.set_item("total_fields", total_fields).unwrap();
    completeness.set_item("filled_fields", 0).unwrap();
    completeness.set_item("missing_required", required_count).unwrap();
    let pct = if total_fields > 0 { 0.0_f64 } else { 100.0_f64 };
    completeness.set_item("completion_pct", pct).unwrap();
    completeness.set_item("status", "incomplete").unwrap();

    template.set_item("completeness", completeness).unwrap();
    root.set_item("template", template).unwrap();

    root.unbind()
}

// ═══════════════════════════════════════════════════════════════
//  Template Validation
// ═══════════════════════════════════════════════════════════════

/// Validate a template dict for completeness.
///
/// Checks all fields in all sections and counts:
/// - How many fields have a non-null, non-empty value
/// - How many required fields are still missing
/// - Overall completion percentage
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict (as returned by ``template_generate``).
///
/// Returns
/// -------
/// dict
///     Validation result with keys:
///     - ``valid`` (bool): True if all required fields are filled
///     - ``total_fields`` (int): Total field count
///     - ``filled_fields`` (int): Fields with values
///     - ``missing_required`` (int): Required fields without values
///     - ``completion_pct`` (float): 0.0-100.0
///     - ``status`` (str): "complete", "partial", or "incomplete"
///     - ``missing_field_names`` (list[str]): Names of missing required fields
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

            // Skip metadata keys (start with _)
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

// ═══════════════════════════════════════════════════════════════
//  Missing Fields
// ═══════════════════════════════════════════════════════════════

/// List all missing required fields in a template.
///
/// This function is used by the interactive agent to determine
/// what data to ask the user for next.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict (as returned by ``template_generate``).
///
/// Returns
/// -------
/// list[dict]
///     Each dict contains:
///     - ``name`` (str): Field name
///     - ``display_name`` (str): Human-readable name
///     - ``type`` (str): Field type string
///     - ``section`` (str): Section ID
///     - ``description`` (str): Field description
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

            // This is a missing required field — build info dict
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

// ═══════════════════════════════════════════════════════════════
//  Fill Field Value
// ═══════════════════════════════════════════════════════════════

/// Fill a field value in a template dict.
///
/// This function is used by the interactive agent to set a
/// field value after the user provides data.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict (will be modified in-place).
/// section_id : str
///     The section containing the field.
/// field_name : str
///     The field name to set.
/// value : any
///     The value to set.
///
/// Returns
/// -------
/// bool
///     True if the field was found and set, False otherwise.
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
            if let Some(status) = validation.get_item("status").ok().flatten() {
                comp_dict.set_item("status", status)?;
            }
            // Also update the top-level metadata status
            if let Some(meta) = template_pydict.get_item("metadata").ok().flatten() {
                if let Ok(meta_dict) = meta.downcast::<PyDict>() {
                    meta_dict.set_item("status", status)?;
                }
            }
        }
    }

    Ok(true)
}

// ═══════════════════════════════════════════════════════════════
//  Template to YAML String
// ═══════════════════════════════════════════════════════════════

/// Serialize a template dict to a YAML string.
///
/// Uses Python's yaml module for serialization. If yaml is not
/// available, falls back to JSON serialization.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict.
///
/// Returns
/// -------
/// str
///     YAML string representation of the template.
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

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════
//
// Note: PyO3-dependent tests (template_generate, template_validate,
// template_set_field) require a Python interpreter. These are tested
// via the Python bridge (src/core/niche_rust/bridge.py) using pytest
// after `maturin develop`. The tests below verify pure Rust logic.

#[cfg(test)]
mod tests {
    use super::*;
    use crate::niche::{DataSensitivity, FieldRequirement, NicheCategory,
                       NicheDefinition, TemplateFieldType};

    #[test]
    fn test_catalog_lookup_for_template() {
        // Verify catalog has the niches that template_generate depends on
        let niche = catalog_get_by_id("telemedicine");
        assert!(niche.is_some());
        assert_eq!(niche.unwrap().niche_id(), "telemedicine");
    }

    #[test]
    fn test_catalog_lookup_returns_none_for_invalid() {
        let niche = catalog_get_by_id("nonexistent_niche");
        assert!(niche.is_none());
    }

    #[test]
    fn test_niche_definition_field_counts() {
        let niche = catalog_get_by_id("ai_automation").unwrap();
        assert!(niche.total_field_count() > 0);
        assert!(niche.required_field_count() > 0);
        assert!(niche.required_field_count() <= niche.total_field_count());
    }

    #[test]
    fn test_all_niches_have_sections_for_template() {
        let ids = crate::catalog::catalog_ids();
        for id in ids {
            let niche = catalog_get_by_id(&id).unwrap();
            assert!(
                niche.section_count() >= 2,
                "Niche {} should have at least 2 sections, got {}",
                id,
                niche.section_count(),
            );
        }
    }

    #[test]
    fn test_template_field_type_completeness() {
        // Verify all field types have valid as_str representations
        assert_eq!(TemplateFieldType::Text.as_str(), "text");
        assert_eq!(TemplateFieldType::Number.as_str(), "number");
        assert_eq!(TemplateFieldType::Boolean.as_str(), "boolean");
        assert_eq!(TemplateFieldType::Date.as_str(), "date");
        assert_eq!(TemplateFieldType::DateTime.as_str(), "datetime");
        assert_eq!(TemplateFieldType::Email.as_str(), "email");
        assert_eq!(TemplateFieldType::Url.as_str(), "url");
        assert_eq!(TemplateFieldType::Phone.as_str(), "phone");
        assert_eq!(TemplateFieldType::Currency.as_str(), "currency");
        assert_eq!(TemplateFieldType::Percentage.as_str(), "percentage");
        assert_eq!(TemplateFieldType::Json.as_str(), "json");
        assert_eq!(TemplateFieldType::Enum.as_str(), "enum");
        assert_eq!(TemplateFieldType::Reference.as_str(), "reference");
        assert_eq!(TemplateFieldType::File.as_str(), "file");
    }

    #[test]
    fn test_field_requirement_values() {
        assert_eq!(FieldRequirement::Required.as_str(), "required");
        assert_eq!(FieldRequirement::Optional.as_str(), "optional");
        assert_eq!(FieldRequirement::Conditional.as_str(), "conditional");
    }
}
