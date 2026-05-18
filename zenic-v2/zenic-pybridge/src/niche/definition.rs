// ─── NicheDefinition ─────────────────────────────────────────────────────
// Complete niche definition type with PyO3 bindings

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};

use super::api::log_niche_error;
use super::enums::{DataSensitivity, NicheCategory};
use super::schema::TemplateSection;

// ═══════════════════════════════════════════════════════════════
//  NicheDefinition — complete niche definition
// ═══════════════════════════════════════════════════════════════

/// A complete, Rust-compiled niche definition.
///
/// This is the core type of the new niche architecture. Each
/// NicheDefinition is compiled into the Rust binary (no YAML
/// loading at runtime) and serves as the blueprint for:
///
/// 1. Dynamic YAML template generation (template.rs)
/// 2. Interactive data collection (future phases)
/// 3. CertifiedBlueprint conversion (bridge to Phase 5 system)
///
/// # Key Design Decisions
///
/// - All fields are read-only from Python (private + getters)
/// - template_sections define the structure of the generated template
/// - required_documents lists what document types the user should upload
/// - compliance and data_sensitivity determine Blueprint tier
#[pyclass(name = "NicheDefinition")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct NicheDefinition {
    niche_id: String,
    name: String,
    category: NicheCategory,
    description: String,
    domain: String,
    subdomain: String,
    scale: String,
    tags: Vec<String>,
    template_sections: Vec<TemplateSection>,
    required_documents: Vec<String>,
    compliance: Vec<String>,
    data_sensitivity: DataSensitivity,
    version: String,
    author: String,
}

impl NicheDefinition {
    /// Create a new NicheDefinition with required fields.
    pub fn new(
        niche_id: String,
        name: String,
        category: NicheCategory,
        description: String,
        domain: String,
        data_sensitivity: DataSensitivity,
    ) -> Self {
        let niche_id_trimmed = niche_id.trim().to_string();
        if niche_id_trimmed.is_empty() {
            log_niche_error("NicheDefinition: niche_id cannot be empty");
        }
        NicheDefinition {
            niche_id: niche_id_trimmed,
            name,
            category,
            description,
            domain,
            subdomain: String::new(),
            scale: "medium".to_string(),
            tags: Vec::new(),
            template_sections: Vec::new(),
            required_documents: Vec::new(),
            compliance: Vec::new(),
            data_sensitivity,
            version: "1.0.0".to_string(),
            author: "zenic-agents".to_string(),
        }
    }

    /// Add a template section.
    pub fn add_section(&mut self, section: TemplateSection) {
        self.template_sections.push(section);
    }

    /// Set the subdomain (used by catalog builders).
    pub(crate) fn set_subdomain(&mut self, value: String) {
        self.subdomain = value;
    }

    /// Set the scale (used by catalog builders).
    pub(crate) fn set_scale(&mut self, value: String) {
        self.scale = value;
    }

    /// Set the tags (used by catalog builders).
    pub(crate) fn set_tags(&mut self, value: Vec<String>) {
        self.tags = value;
    }

    /// Set the required_documents (used by catalog builders).
    pub(crate) fn set_required_documents(&mut self, value: Vec<String>) {
        self.required_documents = value;
    }

    /// Set the compliance list (used by catalog builders).
    pub(crate) fn set_compliance(&mut self, value: Vec<String>) {
        self.compliance = value;
    }

    /// Get the niche_id.
    pub fn niche_id(&self) -> &str {
        &self.niche_id
    }

    /// Get the category.
    pub fn category(&self) -> NicheCategory {
        self.category
    }

    /// Get the data_sensitivity.
    pub fn data_sensitivity(&self) -> DataSensitivity {
        self.data_sensitivity
    }

    /// Get all template sections.
    pub fn template_sections(&self) -> &[TemplateSection] {
        &self.template_sections
    }

    /// Count all fields across all sections.
    pub fn total_field_count(&self) -> usize {
        self.template_sections.iter().map(|s| s.fields().len()).sum()
    }

    /// Count required fields across all sections.
    pub fn required_field_count(&self) -> usize {
        self.template_sections
            .iter()
            .map(|s| s.required_field_count())
            .sum()
    }
}

#[pymethods]
impl NicheDefinition {
    #[getter]
    fn niche_id(&self) -> &str {
        &self.niche_id
    }

    #[getter]
    fn name(&self) -> &str {
        &self.name
    }

    #[getter]
    fn category(&self) -> NicheCategory {
        self.category
    }

    #[getter]
    fn description(&self) -> &str {
        &self.description
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
    fn scale(&self) -> &str {
        &self.scale
    }

    #[getter]
    fn tags(&self) -> Vec<String> {
        self.tags.clone()
    }

    #[getter]
    fn required_documents(&self) -> Vec<String> {
        self.required_documents.clone()
    }

    #[getter]
    fn compliance(&self) -> Vec<String> {
        self.compliance.clone()
    }

    #[getter]
    fn data_sensitivity(&self) -> DataSensitivity {
        self.data_sensitivity
    }

    #[getter]
    fn version(&self) -> &str {
        &self.version
    }

    #[getter]
    fn author(&self) -> &str {
        &self.author
    }

    /// Get the number of template sections.
    fn section_count(&self) -> usize {
        self.template_sections.len()
    }

    /// Count all fields across all sections.
    fn total_fields(&self) -> usize {
        self.total_field_count()
    }

    /// Count required fields across all sections.
    fn required_fields(&self) -> usize {
        self.required_field_count()
    }

    /// Get a section by section_id. Returns None if not found.
    fn get_section(&self, section_id: &str) -> Option<TemplateSection> {
        self.template_sections
            .iter()
            .find(|s| s.section_id() == section_id)
            .cloned()
    }

    /// Get all section IDs.
    fn section_ids(&self) -> Vec<String> {
        self.template_sections
            .iter()
            .map(|s| s.section_id().to_string())
            .collect()
    }

    /// Check if this niche requires a specific compliance standard.
    fn has_compliance(&self, standard: &str) -> bool {
        self.compliance
            .iter()
            .any(|c| c.eq_ignore_ascii_case(standard))
    }

    /// Get a summary dict for display purposes.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("niche_id", &self.niche_id)?;
        dict.set_item("name", &self.name)?;
        dict.set_item("category", self.category.as_str())?;
        dict.set_item("domain", &self.domain)?;
        dict.set_item("subdomain", &self.subdomain)?;
        dict.set_item("scale", &self.scale)?;
        dict.set_item("data_sensitivity", self.data_sensitivity.as_str())?;
        dict.set_item("sections", self.template_sections.len())?;
        dict.set_item("total_fields", self.total_field_count())?;
        dict.set_item("required_fields", self.required_field_count())?;
        dict.set_item("compliance", self.compliance.clone())?;
        dict.set_item("required_documents", self.required_documents.clone())?;
        dict.set_item("version", &self.version)?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "NicheDefinition(id={:?}, name={:?}, category={}, sensitivity={})",
            self.niche_id,
            self.name,
            self.category.as_str(),
            self.data_sensitivity.as_str(),
        )
    }
}
