//! Niche Core Types — Rust-compiled niche definitions for Zenic-Agents.
//!
//! This module defines the core data types for the new niche architecture
//! where niches are compiled into Rust (not static YAML) and serve as
//! the foundation for dynamic YAML template generation.
//!
//! # Architecture
//!
//! Each NicheDefinition contains:
//! - Identity: niche_id, name, category, domain
//! - Template sections: structured fields that form the YAML template
//! - Metadata: compliance, data_sensitivity, scale, required_documents
//!
//! The flow is:
//! 1. User selects a NicheDefinition from the catalog
//! 2. NicheDefinition → TemplateSchema (via template.rs)
//! 3. User uploads documents → agent fills template fields
//! 4. Agent asks user for missing required fields
//! 5. Completed template → CertifiedBlueprint (via blueprints)
//!
//! # PyO3 Exposed Types
//!
//! - `NicheCategory` — 7 industry categories
//! - `DataSensitivity` — 4 sensitivity levels
//! - `FieldRequirement` — required / optional / conditional
//! - `TemplateFieldType` — 14 field types for template schemas
//! - `TemplateFieldSchema` — single field definition
//! - `TemplateSection` — group of related fields
//! - `NicheDefinition` — complete niche definition

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;

// ═══════════════════════════════════════════════════════════════
//  NicheCategory — 7 cutting-edge industry categories
// ═══════════════════════════════════════════════════════════════

/// Industry category for a niche.
///
/// Each category groups related niches that share compliance
/// requirements, data sensitivity patterns, and workflow structures.
///
/// ======== ============ ===================================
/// Variant  Python value Description
/// ======== ============ ===================================
/// AiData   ``"ai_data"`` AI, ML, NLP, Data Analytics
/// FinTech  ``"fintech"`` DeFi, Neo-banking, InsurTech, RegTech
/// HealthTech ``"healthtech"`` Telemedicine, Genomics, Wearables
/// GreenTech ``"greentech"`` Carbon, Smart Grid, Circular Economy
/// EdTech   ``"edtech"`` Adaptive Learning, VR, Micro-credentials
/// PropTech ``"proptech"`` Smart Buildings, Digital Twins
/// LegalTech ``"legaltech"`` Smart Contracts, Legal AI, Compliance
/// ======== ============ ===================================
#[pyclass(name = "NicheCategory", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum NicheCategory {
    AiData,
    FinTech,
    HealthTech,
    GreenTech,
    EdTech,
    PropTech,
    LegalTech,
}

impl NicheCategory {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            NicheCategory::AiData => "ai_data",
            NicheCategory::FinTech => "fintech",
            NicheCategory::HealthTech => "healthtech",
            NicheCategory::GreenTech => "greentech",
            NicheCategory::EdTech => "edtech",
            NicheCategory::PropTech => "proptech",
            NicheCategory::LegalTech => "legaltech",
        }
    }

    /// Human-readable display name.
    pub fn display_name(&self) -> &'static str {
        match self {
            NicheCategory::AiData => "AI & Data",
            NicheCategory::FinTech => "FinTech",
            NicheCategory::HealthTech => "HealthTech",
            NicheCategory::GreenTech => "GreenTech",
            NicheCategory::EdTech => "EdTech",
            NicheCategory::PropTech => "PropTech",
            NicheCategory::LegalTech => "LegalTech",
        }
    }

    /// All variants in catalog order.
    pub fn all() -> &'static [NicheCategory] {
        &[
            NicheCategory::AiData,
            NicheCategory::FinTech,
            NicheCategory::HealthTech,
            NicheCategory::GreenTech,
            NicheCategory::EdTech,
            NicheCategory::PropTech,
            NicheCategory::LegalTech,
        ]
    }
}

#[pymethods]
impl NicheCategory {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("NicheCategory.{}", self.display_name().replace(' ', ""))
    }
}

// ═══════════════════════════════════════════════════════════════
//  DataSensitivity — 4 sensitivity levels
// ═══════════════════════════════════════════════════════════════

/// Data sensitivity classification for a niche.
///
/// Maps directly to BlueprintTier and SafetyGate behavior:
///
/// ======== ============ ============= ===================================
/// Variant  Python value BlueprintTier Description
/// ======== ============ ============= ===================================
/// Low      ``"low"``    FREE          Public data, no PII
/// Medium   ``"medium"`` FREE          Internal data, limited PII
/// High     ``"high"``   PRO           Sensitive data, significant PII
/// Critical ``"critical"`` ENTERPRISE  Regulated data (HIPAA, PCI, GDPR)
/// ======== ============ ============= ===================================
#[pyclass(name = "DataSensitivity", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum DataSensitivity {
    Low,
    Medium,
    High,
    Critical,
}

impl DataSensitivity {
    pub fn as_str(&self) -> &'static str {
        match self {
            DataSensitivity::Low => "low",
            DataSensitivity::Medium => "medium",
            DataSensitivity::High => "high",
            DataSensitivity::Critical => "critical",
        }
    }
}

#[pymethods]
impl DataSensitivity {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("DataSensitivity.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  FieldRequirement — field requirement classification
// ═══════════════════════════════════════════════════════════════

/// Whether a template field is required, optional, or conditional.
///
/// Conditional fields require a condition expression that determines
/// at runtime whether the field is needed (e.g., "has_insurance == true").
#[pyclass(name = "FieldRequirement", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum FieldRequirement {
    Required,
    Optional,
    Conditional,
}

impl FieldRequirement {
    pub fn as_str(&self) -> &'static str {
        match self {
            FieldRequirement::Required => "required",
            FieldRequirement::Optional => "optional",
            FieldRequirement::Conditional => "conditional",
        }
    }
}

#[pymethods]
impl FieldRequirement {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("FieldRequirement.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  TemplateFieldType — 14 field types for template schemas
// ═══════════════════════════════════════════════════════════════

/// Type of a template field, controlling validation and UI rendering.
///
/// Each variant maps to a specific input widget and validation rule
/// in the frontend. Reference fields link to other entities.
/// File fields specify accepted MIME types for document uploads.
#[pyclass(name = "TemplateFieldType", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum TemplateFieldType {
    Text,
    Number,
    Boolean,
    Date,
    DateTime,
    Email,
    Url,
    Phone,
    Currency,
    Percentage,
    Json,
    Enum,
    Reference,
    File,
}

impl TemplateFieldType {
    pub fn as_str(&self) -> &'static str {
        match self {
            TemplateFieldType::Text => "text",
            TemplateFieldType::Number => "number",
            TemplateFieldType::Boolean => "boolean",
            TemplateFieldType::Date => "date",
            TemplateFieldType::DateTime => "datetime",
            TemplateFieldType::Email => "email",
            TemplateFieldType::Url => "url",
            TemplateFieldType::Phone => "phone",
            TemplateFieldType::Currency => "currency",
            TemplateFieldType::Percentage => "percentage",
            TemplateFieldType::Json => "json",
            TemplateFieldType::Enum => "enum",
            TemplateFieldType::Reference => "reference",
            TemplateFieldType::File => "file",
        }
    }
}

#[pymethods]
impl TemplateFieldType {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("TemplateFieldType.{}", self.as_str().to_uppercase())
    }
}

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
///
/// Sections provide structure to the YAML template and the
/// interactive data collection flow. Each section has:
/// - section_id: machine-readable identifier (used as YAML key)
/// - title: human-readable title
/// - description: explanation of the section's purpose
/// - fields: ordered list of field schemas
/// - order: display ordering among sections
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
        self.template_sections.iter().map(|s| s.fields.len()).sum()
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
            .find(|s| s.section_id == section_id)
            .cloned()
    }

    /// Get all section IDs.
    fn section_ids(&self) -> Vec<String> {
        self.template_sections
            .iter()
            .map(|s| s.section_id.clone())
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

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers
// ═══════════════════════════════════════════════════════════════

/// Log a niche-related error without panicking.
fn log_niche_error(msg: &str) {
    eprintln!("[ZENIC-NICHE-ERROR] {}", msg);
}

// ═══════════════════════════════════════════════════════════════
//  PyO3 Utility Functions
// ═══════════════════════════════════════════════════════════════

/// Get all available niche categories as a list of strings.
#[pyfunction]
pub fn get_niche_categories(py: Python<'_>) -> PyResult<Vec<String>> {
    Ok(NicheCategory::all().iter().map(|c| c.as_str().to_string()).collect())
}

/// Get display names for all niche categories.
#[pyfunction]
pub fn get_niche_category_display_names(py: Python<'_>) -> PyResult<Vec<String>> {
    Ok(NicheCategory::all().iter().map(|c| c.display_name().to_string()).collect())
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_niche_category_str_roundtrip() {
        assert_eq!(NicheCategory::AiData.as_str(), "ai_data");
        assert_eq!(NicheCategory::FinTech.as_str(), "fintech");
        assert_eq!(NicheCategory::HealthTech.as_str(), "healthtech");
        assert_eq!(NicheCategory::GreenTech.as_str(), "greentech");
        assert_eq!(NicheCategory::EdTech.as_str(), "edtech");
        assert_eq!(NicheCategory::PropTech.as_str(), "proptech");
        assert_eq!(NicheCategory::LegalTech.as_str(), "legaltech");
    }

    #[test]
    fn test_niche_category_display_names() {
        assert_eq!(NicheCategory::AiData.display_name(), "AI & Data");
        assert_eq!(NicheCategory::FinTech.display_name(), "FinTech");
        assert_eq!(NicheCategory::HealthTech.display_name(), "HealthTech");
        assert_eq!(NicheCategory::GreenTech.display_name(), "GreenTech");
        assert_eq!(NicheCategory::EdTech.display_name(), "EdTech");
        assert_eq!(NicheCategory::PropTech.display_name(), "PropTech");
        assert_eq!(NicheCategory::LegalTech.display_name(), "LegalTech");
    }

    #[test]
    fn test_niche_category_all_count() {
        assert_eq!(NicheCategory::all().len(), 7);
    }

    #[test]
    fn test_data_sensitivity_str_roundtrip() {
        assert_eq!(DataSensitivity::Low.as_str(), "low");
        assert_eq!(DataSensitivity::Medium.as_str(), "medium");
        assert_eq!(DataSensitivity::High.as_str(), "high");
        assert_eq!(DataSensitivity::Critical.as_str(), "critical");
    }

    #[test]
    fn test_field_requirement_str_roundtrip() {
        assert_eq!(FieldRequirement::Required.as_str(), "required");
        assert_eq!(FieldRequirement::Optional.as_str(), "optional");
        assert_eq!(FieldRequirement::Conditional.as_str(), "conditional");
    }

    #[test]
    fn test_template_field_type_count() {
        // 14 field types
        let types = [
            TemplateFieldType::Text,
            TemplateFieldType::Number,
            TemplateFieldType::Boolean,
            TemplateFieldType::Date,
            TemplateFieldType::DateTime,
            TemplateFieldType::Email,
            TemplateFieldType::Url,
            TemplateFieldType::Phone,
            TemplateFieldType::Currency,
            TemplateFieldType::Percentage,
            TemplateFieldType::Json,
            TemplateFieldType::Enum,
            TemplateFieldType::Reference,
            TemplateFieldType::File,
        ];
        assert_eq!(types.len(), 14);
    }

    #[test]
    fn test_template_field_schema_creation() {
        let field = TemplateFieldSchema::new(
            "email".to_string(),
            "Email Address".to_string(),
            TemplateFieldType::Email,
            FieldRequirement::Required,
        );
        assert_eq!(field.name(), "email");
        assert_eq!(field.display_name(), "Email Address");
        assert!(field.is_required());
        assert!(!field.is_conditional());
    }

    #[test]
    fn test_template_section_creation() {
        let mut section = TemplateSection::new(
            "contact_info".to_string(),
            "Contact Information".to_string(),
        );
        let field = TemplateFieldSchema::new(
            "phone".to_string(),
            "Phone Number".to_string(),
            TemplateFieldType::Phone,
            FieldRequirement::Optional,
        );
        section.add_field(field);
        assert_eq!(section.section_id(), "contact_info");
        assert_eq!(section.field_count(), 1);
        assert_eq!(section.required_count(), 0);
    }

    #[test]
    fn test_niche_definition_creation() {
        let niche = NicheDefinition::new(
            "test_niche".to_string(),
            "Test Niche".to_string(),
            NicheCategory::AiData,
            "A test niche for unit testing".to_string(),
            "testing".to_string(),
            DataSensitivity::Low,
        );
        assert_eq!(niche.niche_id(), "test_niche");
        assert_eq!(niche.category(), NicheCategory::AiData);
        assert_eq!(niche.data_sensitivity(), DataSensitivity::Low);
        assert_eq!(niche.total_fields(), 0);
        assert_eq!(niche.required_fields(), 0);
    }

    #[test]
    fn test_niche_definition_with_sections() {
        let mut niche = NicheDefinition::new(
            "ai_automation".to_string(),
            "AI Automation".to_string(),
            NicheCategory::AiData,
            "AI automation platform".to_string(),
            "ai".to_string(),
            DataSensitivity::High,
        );
        let mut section = TemplateSection::new(
            "model_config".to_string(),
            "Model Configuration".to_string(),
        );
        section.add_field(TemplateFieldSchema::new(
            "model_name".to_string(),
            "Model Name".to_string(),
            TemplateFieldType::Text,
            FieldRequirement::Required,
        ));
        section.add_field(TemplateFieldSchema::new(
            "temperature".to_string(),
            "Temperature".to_string(),
            TemplateFieldType::Number,
            FieldRequirement::Optional,
        ));
        niche.add_section(section);
        assert_eq!(niche.total_fields(), 2);
        assert_eq!(niche.required_fields(), 1);
    }

    #[test]
    fn test_template_field_schema_empty_name() {
        // Should not panic, just log error
        let field = TemplateFieldSchema::new(
            "  ".to_string(),
            "Empty".to_string(),
            TemplateFieldType::Text,
            FieldRequirement::Required,
        );
        // Name is trimmed
        assert_eq!(field.name(), "");
    }

    #[test]
    fn test_niche_definition_compliance_check() {
        let mut niche = NicheDefinition::new(
            "health_niche".to_string(),
            "Health Niche".to_string(),
            NicheCategory::HealthTech,
            "Health platform".to_string(),
            "health".to_string(),
            DataSensitivity::Critical,
        );
        niche.set_compliance(vec!["HIPAA".to_string(), "GDPR".to_string()]);
        assert!(niche.has_compliance("HIPAA"));
        assert!(niche.has_compliance("hipaa"));
        assert!(niche.has_compliance("GDPR"));
        assert!(!niche.has_compliance("PCI"));
    }
}
