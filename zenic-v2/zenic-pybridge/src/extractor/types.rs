//! Field extraction types — FieldMatch, ExtractionResult, and constants.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Minimum confidence to consider a match valid.
pub(crate) const MIN_CONFIDENCE_THRESHOLD: f64 = 0.3;

/// Confidence level for exact name match.
pub(crate) const CONFIDENCE_EXACT: f64 = 0.95;

/// Confidence level for display name match.
pub(crate) const CONFIDENCE_DISPLAY: f64 = 0.85;

/// Confidence level for stem/substring match.
pub(crate) const CONFIDENCE_STEM: f64 = 0.70;

/// Confidence level for keyword match.
pub(crate) const CONFIDENCE_KEYWORD: f64 = 0.50;

/// Confidence level for heuristic/type match.
pub(crate) const CONFIDENCE_HEURISTIC: f64 = 0.30;

/// Maximum number of candidate values to extract per field.
pub(crate) const MAX_CANDIDATES_PER_FIELD: usize = 5;

/// Common field name aliases for fuzzy matching.
pub(crate) const FIELD_ALIASES: &[(&str, &[&str])] = &[
    ("business_name", &["company", "organization", "empresa", "negocio", "company_name", "business", "firm"]),
    ("business_type", &["company_type", "entity_type", "tipo_empresa", "organization_type"]),
    ("tax_id", &["ruc", "nit", "cif", "vat", "eIN", "tax_number", "rfc"]),
    ("country", &["pais", "nation", "region"]),
    ("industry", &["sector", "industria", "vertical", "domain"]),
    ("website", &["url", "sitio_web", "web", "homepage", "site"]),
    ("email", &["correo", "mail", "e-mail", "email_address"]),
    ("phone", &["telefono", "tel", "telephone", "phone_number", "contact_number"]),
    ("admin_email", &["admin_correo", "administrator_email", "admin_mail"]),
    ("admin_phone", &["admin_telefono", "administrator_phone"]),
    ("auth_method", &["authentication", "auth_type", "metodo_autenticacion"]),
    ("model_name", &["modelo", "model", "ai_model"]),
    ("model_provider", &["provider", "proveedor", "ai_provider"]),
    ("api_key_ref", &["api_key", "key_ref", "clave_api"]),
    ("base_currency", &["currency", "moneda", "moneda_base"]),
    ("payment_gateway", &["gateway", "pasarela", "payment_provider"]),
];

// ═══════════════════════════════════════════════════════════════
//  FieldMatch — a single matched field with confidence
// ═══════════════════════════════════════════════════════════════

/// A field matched from extracted text with confidence score.
///
/// Each match records:
/// - Which template field it corresponds to
/// - The extracted value
/// - Confidence score (0.0-1.0)
/// - The source document/section
/// - The matching method used
#[pyclass(name = "FieldMatch")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FieldMatch {
    field_name: String,
    section_id: String,
    value: String,
    confidence: f64,
    source: String,
    match_method: String,
}

impl FieldMatch {
    /// Create a new FieldMatch with validation.
    pub fn new(
        field_name: String,
        section_id: String,
        value: String,
        confidence: f64,
        source: String,
        match_method: String,
    ) -> Self {
        let confidence_clamped = confidence.clamp(0.0, 1.0);
        FieldMatch {
            field_name,
            section_id,
            value,
            confidence: confidence_clamped,
            source,
            match_method,
        }
    }

    /// Get the field name.
    pub fn field_name(&self) -> &str {
        &self.field_name
    }

    /// Get the section ID.
    pub fn section_id(&self) -> &str {
        &self.section_id
    }

    /// Get the matched value.
    pub fn value(&self) -> &str {
        &self.value
    }

    /// Get the confidence score.
    pub fn confidence(&self) -> f64 {
        self.confidence
    }
}

#[pymethods]
impl FieldMatch {
    #[getter]
    fn field_name(&self) -> &str {
        &self.field_name
    }

    #[getter]
    fn section_id(&self) -> &str {
        &self.section_id
    }

    #[getter]
    fn value(&self) -> &str {
        &self.value
    }

    #[getter]
    fn confidence(&self) -> f64 {
        self.confidence
    }

    #[getter]
    fn source(&self) -> &str {
        &self.source
    }

    #[getter]
    fn match_method(&self) -> &str {
        &self.match_method
    }

    /// Check if this match meets the minimum confidence threshold.
    fn is_reliable(&self) -> bool {
        self.confidence >= MIN_CONFIDENCE_THRESHOLD
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("field_name", &self.field_name)?;
        dict.set_item("section_id", &self.section_id)?;
        dict.set_item("value", &self.value)?;
        dict.set_item("confidence", self.confidence)?;
        dict.set_item("source", &self.source)?;
        dict.set_item("match_method", &self.match_method)?;
        dict.set_item("is_reliable", self.is_reliable())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "FieldMatch(field={:?}, section={:?}, confidence={:.2}, method={:?})",
            self.field_name, self.section_id, self.confidence, self.match_method,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  ExtractionResult — results from field extraction
// ═══════════════════════════════════════════════════════════════

/// Results from extracting field values from text.
///
/// Contains all matches, unmatched fields, and aggregate statistics.
#[pyclass(name = "ExtractionResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExtractionResult {
    matches: Vec<FieldMatch>,
    unmatched_fields: Vec<String>,
    confidence_avg: f64,
    total_candidates: usize,
    matched_count: usize,
    reliable_count: usize,
}

impl ExtractionResult {
    pub fn new(
        matches: Vec<FieldMatch>,
        unmatched_fields: Vec<String>,
        confidence_avg: f64,
        total_candidates: usize,
        matched_count: usize,
        reliable_count: usize,
    ) -> Self {
        ExtractionResult {
            matches,
            unmatched_fields,
            confidence_avg,
            total_candidates,
            matched_count,
            reliable_count,
        }
    }
}

#[pymethods]
impl ExtractionResult {
    #[getter]
    fn matches(&self) -> Vec<FieldMatch> {
        self.matches.clone()
    }

    #[getter]
    fn unmatched_fields(&self) -> Vec<String> {
        self.unmatched_fields.clone()
    }

    #[getter]
    fn confidence_avg(&self) -> f64 {
        self.confidence_avg
    }

    #[getter]
    fn total_candidates(&self) -> usize {
        self.total_candidates
    }

    #[getter]
    fn matched_count(&self) -> usize {
        self.matched_count
    }

    #[getter]
    fn reliable_count(&self) -> usize {
        self.reliable_count
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("matched_count", self.matched_count)?;
        dict.set_item("unmatched_count", self.unmatched_fields.len())?;
        dict.set_item("confidence_avg", self.confidence_avg)?;
        dict.set_item("reliable_count", self.reliable_count)?;
        dict.set_item("total_candidates", self.total_candidates)?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "ExtractionResult(matched={}, unmatched={}, avg_confidence={:.2})",
            self.matched_count,
            self.unmatched_fields.len(),
            self.confidence_avg,
        )
    }
}
