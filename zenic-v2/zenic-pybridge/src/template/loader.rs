//! Template generation: create YAML template skeletons from niche definitions.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::catalog::catalog_get_by_id;

use super::types::{NicheDefinition, TemplateFieldType};

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
