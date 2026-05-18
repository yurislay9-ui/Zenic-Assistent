// ─── Niche Schema Types ──────────────────────────────────────────────────
// TemplateFieldSchema, TemplateSection

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use super::api::log_niche_error;
use super::enums::{FieldRequirement, TemplateFieldType};

// ═══════════════════════════════════════════════════════════════
//  TemplateFieldSchema — single field definition
// ═══════════════════════════════════════════════════════════════

/// Schema definition for a single field within a template section.
///
/// Each field has:
/// - Identity: name (machine), display_name (human)
/// - Type: TemplateFieldType controlling validation
/// - Requirement: required / optional / conditional
/// - Default: optional default value as string
/// - Validation: key-value validation rules (min, max, pattern, etc.)
/// - Order: display ordering within section
///
/// All fields are read-only from Python via getters.
#[pyclass(name = "TemplateFieldSchema")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TemplateFieldSchema {
    name: String,
    display_name: String,
    field_type: TemplateFieldType,
    requirement: FieldRequirement,
    default_value: Option<String>,
    description: String,
    condition: String,
    validation: HashMap<String, String>,
    enum_variants: Vec<String>,
    reference_entity: String,
    file_accept: Vec<String>,
    order: usize,
}

impl TemplateFieldSchema {
    /// Create a new TemplateFieldSchema with validation.
    pub fn new(
        name: String,
        display_name: String,
        field_type: TemplateFieldType,
        requirement: FieldRequirement,
    ) -> Self {
        let name_trimmed = name.trim().to_string();
        if name_trimmed.is_empty() {
            log_niche_error("TemplateFieldSchema: name cannot be empty");
        }
        TemplateFieldSchema {
            name: name_trimmed,
            display_name,
            field_type,
            requirement,
            default_value: None,
            description: String::new(),
            condition: String::new(),
            validation: HashMap::new(),
            enum_variants: Vec::new(),
            reference_entity: String::new(),
            file_accept: Vec::new(),
            order: 0,
        }
    }

    /// Get the field name (machine-readable identifier).
    pub fn name(&self) -> &str {
        &self.name
    }
}

#[pymethods]
impl TemplateFieldSchema {
    #[getter]
    fn name(&self) -> &str {
        &self.name
    }

    #[getter]
    fn display_name(&self) -> &str {
        &self.display_name
    }

    #[getter]
    fn field_type(&self) -> TemplateFieldType {
        self.field_type
    }

    #[getter]
    fn requirement(&self) -> FieldRequirement {
        self.requirement
    }

    #[getter]
    fn default_value(&self) -> Option<&str> {
        self.default_value.as_deref()
    }

    #[getter]
    fn description(&self) -> &str {
        &self.description
    }

    #[getter]
    fn condition(&self) -> &str {
        &self.condition
    }

    #[getter]
    fn validation(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        for (k, v) in &self.validation {
            dict.set_item(k, v)?;
        }
        Ok(dict.unbind())
    }

    #[getter]
    fn enum_variants(&self) -> Vec<String> {
        self.enum_variants.clone()
    }

    #[getter]
    fn reference_entity(&self) -> &str {
        &self.reference_entity
    }

    #[getter]
    fn file_accept(&self) -> Vec<String> {
        self.file_accept.clone()
    }

    #[getter]
    fn order(&self) -> usize {
        self.order
    }

    /// Check if this field is required.
    fn is_required(&self) -> bool {
        self.requirement == FieldRequirement::Required
    }

    /// Check if this field is conditional.
    fn is_conditional(&self) -> bool {
        self.requirement == FieldRequirement::Conditional
    }

    fn __repr__(&self) -> String {
        format!(
            "TemplateFieldSchema(name={:?}, type={}, requirement={})",
            self.name,
            self.field_type.as_str(),
            self.requirement.as_str(),
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  TemplateSection — group of related fields
// ═══════════════════════════════════════════════════════════════

/// A section within a niche template, grouping related fields.
#[pyclass(name = "TemplateSection")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TemplateSection {
    section_id: String,
    title: String,
    description: String,
    fields: Vec<TemplateFieldSchema>,
    order: usize,
}

impl TemplateSection {
    /// Create a new TemplateSection with the given identity.
    pub fn new(section_id: String, title: String) -> Self {
        TemplateSection {
            section_id,
            title,
            description: String::new(),
            fields: Vec::new(),
            order: 0,
        }
    }

    /// Add a field to this section.
    pub fn add_field(&mut self, field: TemplateFieldSchema) {
        self.fields.push(field);
    }

    /// Set the description (used by catalog builders).
    pub(crate) fn set_description(&mut self, value: String) {
        self.description = value;
    }

    /// Set the display order (used by catalog builders).
    pub(crate) fn set_order(&mut self, value: usize) {
        self.order = value;
    }

    /// Get the section_id.
    pub fn section_id(&self) -> &str {
        &self.section_id
    }

    /// Get all fields.
    pub fn fields(&self) -> &[TemplateFieldSchema] {
        &self.fields
    }

    /// Count required fields.
    pub fn required_field_count(&self) -> usize {
        self.fields.iter().filter(|f| f.is_required()).count()
    }
}

#[pymethods]
impl TemplateSection {
    #[getter]
    fn section_id(&self) -> &str {
        &self.section_id
    }

    #[getter]
    fn title(&self) -> &str {
        &self.title
    }

    #[getter]
    fn description(&self) -> &str {
        &self.description
    }

    #[getter]
    fn order(&self) -> usize {
        self.order
    }

    /// Get the number of fields in this section.
    fn field_count(&self) -> usize {
        self.fields.len()
    }

    /// Get the number of required fields in this section.
    fn required_count(&self) -> usize {
        self.required_field_count()
    }

    /// Get a list of all field names in this section.
    fn field_names(&self) -> Vec<String> {
        self.fields.iter().map(|f| f.name.clone()).collect()
    }

    /// Get a field by name. Returns None if not found.
    fn get_field(&self, name: &str) -> Option<TemplateFieldSchema> {
        self.fields.iter().find(|f| f.name == name).cloned()
    }

    fn __repr__(&self) -> String {
        format!(
            "TemplateSection(id={:?}, title={:?}, fields={})",
            self.section_id,
            self.title,
            self.fields.len(),
        )
    }
}
