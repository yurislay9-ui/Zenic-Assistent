//! Core types and constants for the Template Completion Agent.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Maximum number of Q&A rounds before forcing finalization.
pub const MAX_ROUNDS: usize = 20;

/// Maximum number of questions returned per round.
pub const MAX_QUESTIONS_PER_ROUND: usize = 10;

/// Maximum answer length in characters.
pub const MAX_ANSWER_LENGTH: usize = 10000;

/// Minimum confidence for auto-accepted extraction matches.
pub const AUTO_ACCEPT_CONFIDENCE: f64 = 0.70;

/// Common suggestions per field type.
pub const SUGGESTIONS_BY_TYPE: &[(&str, &[&str])] = &[
    ("auth_method", &["oauth2", "api_key", "saml", "ldap", "basic_auth", "mfa"]),
    ("business_type", &["llc", "corporation", "sole_proprietorship", "partnership", "cooperative", "nonprofit"]),
    ("model_provider", &["openai", "anthropic", "google", "azure", "aws", "huggingface", "local"]),
    ("payment_gateway", &["stripe", "paypal", "mercadopago", "square", "razorpay", "adyen"]),
    ("base_currency", &["USD", "EUR", "GBP", "MXN", "COP", "ARS", "BRL", "CLP", "PEN"]),
    ("trigger_type", &["webhook", "schedule", "event", "manual", "threshold", "data_change"]),
    ("error_handling", &["retry", "fallback", "skip", "abort", "notify", "queue"]),
    ("data_format", &["json", "csv", "xml", "parquet", "avro", "protobuf"]),
    ("source_type", &["api", "database", "file", "stream", "queue", "webhook"]),
    ("export_format", &["pdf", "csv", "excel", "json", "html", "png"]),
    ("monitoring_frequency", &["real_time", "hourly", "daily", "weekly", "monthly"]),
    ("network", &["ethereum", "polygon", "bsc", "arbitrum", "optimism", "solana", "avalanche"]),
    ("product_type", &["life", "health", "auto", "property", "travel", "business"]),
    ("patient_id_format", &["uuid", "sequential", "mrn", "national_id", "custom"]),
    ("primary_language", &["en", "es", "pt", "fr", "de", "it", "ja", "zh", "ko", "ar"]),
];

/// Validation patterns by field type.
pub const EMAIL_PATTERN: &str = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$";
pub const URL_PATTERN: &str = r"^https?://[a-zA-Z0-9.\-_/]+$";
pub const PHONE_PATTERN: &str = r"^[\+]?[\d\s\-\(\)]{7,20}$";
pub const DATE_PATTERN: &str = r"^\d{4}[-/]\d{2}[-/]\d{2}";
pub const DATETIME_PATTERN: &str = r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}";

// ═══════════════════════════════════════════════════════════════
//  CompletionSession — interactive template completion session
// ═══════════════════════════════════════════════════════════════

/// An interactive template completion session.
///
/// Tracks the full lifecycle of filling out a niche template:
/// from initial generation through document ingestion, Q&A
/// rounds, and final completion.
///
/// The session stores the template_dict (Python dict) that is
/// mutated in-place as fields are filled. It also tracks:
/// - Which documents have been ingested
/// - How many Q&A rounds have occurred
/// - Total fields auto-filled vs. manually filled
/// - Any validation errors encountered
#[pyclass(name = "CompletionSession")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompletionSession {
    pub(crate) session_id: String,
    pub(crate) niche_id: String,
    pub(crate) niche_name: String,
    pub(crate) category: String,
    pub(crate) data_sensitivity: String,
    pub(crate) round_count: usize,
    pub(crate) documents_ingested: usize,
    pub(crate) fields_auto_filled: usize,
    pub(crate) fields_manual_filled: usize,
    pub(crate) total_fields: usize,
    pub(crate) required_fields: usize,
    pub(crate) status: String,
    pub(crate) errors: Vec<String>,
    pub(crate) created_at: String,
    pub(crate) updated_at: String,
}

impl CompletionSession {
    /// Create a new CompletionSession with the given niche information.
    pub fn new(
        session_id: String,
        niche_id: String,
        niche_name: String,
        category: String,
        data_sensitivity: String,
        total_fields: usize,
        required_fields: usize,
    ) -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        CompletionSession {
            session_id,
            niche_id,
            niche_name,
            category,
            data_sensitivity,
            round_count: 0,
            documents_ingested: 0,
            fields_auto_filled: 0,
            fields_manual_filled: 0,
            total_fields,
            required_fields,
            status: "initialized".to_string(),
            errors: Vec::new(),
            created_at: now.clone(),
            updated_at: now,
        }
    }

    /// Get the session_id.
    pub fn session_id(&self) -> &str {
        &self.session_id
    }

    /// Get the niche_id.
    pub fn niche_id(&self) -> &str {
        &self.niche_id
    }

    /// Mark that documents have been ingested.
    pub fn add_documents(&mut self, count: usize) {
        self.documents_ingested += count;
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    /// Record auto-filled fields from extraction.
    pub fn add_auto_filled(&mut self, count: usize) {
        self.fields_auto_filled += count;
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    /// Record manually filled fields from user answers.
    pub fn add_manual_filled(&mut self, count: usize) {
        self.fields_manual_filled += count;
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    /// Increment the round counter.
    pub fn increment_round(&mut self) {
        self.round_count += 1;
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    /// Update the status.
    pub fn set_status(&mut self, status: &str) {
        self.status = status.to_string();
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    /// Add an error message.
    pub fn add_error(&mut self, msg: String) {
        self.errors.push(msg);
    }

    /// Get the documents_ingested count.
    pub fn documents_ingested(&self) -> usize {
        self.documents_ingested
    }
}

#[pymethods]
impl CompletionSession {
    #[getter]
    fn session_id(&self) -> &str {
        &self.session_id
    }

    #[getter]
    fn niche_id(&self) -> &str {
        &self.niche_id
    }

    #[getter]
    fn niche_name(&self) -> &str {
        &self.niche_name
    }

    #[getter]
    fn category(&self) -> &str {
        &self.category
    }

    #[getter]
    fn data_sensitivity(&self) -> &str {
        &self.data_sensitivity
    }

    #[getter]
    fn round_count(&self) -> usize {
        self.round_count
    }

    #[getter]
    fn documents_ingested(&self) -> usize {
        self.documents_ingested
    }

    #[getter]
    fn fields_auto_filled(&self) -> usize {
        self.fields_auto_filled
    }

    #[getter]
    fn fields_manual_filled(&self) -> usize {
        self.fields_manual_filled
    }

    #[getter]
    fn total_fields(&self) -> usize {
        self.total_fields
    }

    #[getter]
    fn required_fields(&self) -> usize {
        self.required_fields
    }

    #[getter]
    fn status(&self) -> &str {
        &self.status
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    #[getter]
    fn has_errors(&self) -> bool {
        !self.errors.is_empty()
    }

    #[getter]
    fn created_at(&self) -> &str {
        &self.created_at
    }

    #[getter]
    fn updated_at(&self) -> &str {
        &self.updated_at
    }

    /// Get a summary dict for display purposes.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("session_id", &self.session_id)?;
        dict.set_item("niche_id", &self.niche_id)?;
        dict.set_item("niche_name", &self.niche_name)?;
        dict.set_item("category", &self.category)?;
        dict.set_item("data_sensitivity", &self.data_sensitivity)?;
        dict.set_item("status", &self.status)?;
        dict.set_item("round_count", self.round_count)?;
        dict.set_item("documents_ingested", self.documents_ingested)?;
        dict.set_item("fields_auto_filled", self.fields_auto_filled)?;
        dict.set_item("fields_manual_filled", self.fields_manual_filled)?;
        dict.set_item("total_fields", self.total_fields)?;
        dict.set_item("required_fields", self.required_fields)?;
        dict.set_item("error_count", self.errors.len())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CompletionSession(id={:?}, niche={:?}, status={}, round={}, auto={}, manual={})",
            self.session_id,
            self.niche_id,
            self.status,
            self.round_count,
            self.fields_auto_filled,
            self.fields_manual_filled,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  CompletionQuestion — structured question for a missing field
// ═══════════════════════════════════════════════════════════════

/// A structured question for a missing required template field.
///
/// Contains all information needed for the frontend to render
/// an appropriate input widget and collect the user's answer.
#[pyclass(name = "CompletionQuestion")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompletionQuestion {
    pub(crate) field_name: String,
    pub(crate) display_name: String,
    pub(crate) field_type: String,
    pub(crate) section_id: String,
    pub(crate) description: String,
    pub(crate) is_required: bool,
    pub(crate) order: usize,
    pub(crate) suggestions: Vec<String>,
    pub(crate) enum_variants: Vec<String>,
    pub(crate) default_value: Option<String>,
    pub(crate) validation_hint: String,
}

impl CompletionQuestion {
    /// Create a new CompletionQuestion.
    pub fn new(
        field_name: String,
        display_name: String,
        field_type: String,
        section_id: String,
    ) -> Self {
        CompletionQuestion {
            field_name,
            display_name,
            field_type,
            section_id,
            description: String::new(),
            is_required: true,
            order: 0,
            suggestions: Vec::new(),
            enum_variants: Vec::new(),
            default_value: None,
            validation_hint: String::new(),
        }
    }

    /// Get the field_name.
    pub fn field_name(&self) -> &str {
        &self.field_name
    }

    /// Get the section_id.
    pub fn section_id(&self) -> &str {
        &self.section_id
    }
}

#[pymethods]
impl CompletionQuestion {
    #[getter]
    fn field_name(&self) -> &str {
        &self.field_name
    }

    #[getter]
    fn display_name(&self) -> &str {
        &self.display_name
    }

    #[getter]
    fn field_type(&self) -> &str {
        &self.field_type
    }

    #[getter]
    fn section_id(&self) -> &str {
        &self.section_id
    }

    #[getter]
    fn description(&self) -> &str {
        &self.description
    }

    #[getter]
    fn is_required(&self) -> bool {
        self.is_required
    }

    #[getter]
    fn order(&self) -> usize {
        self.order
    }

    #[getter]
    fn suggestions(&self) -> Vec<String> {
        self.suggestions.clone()
    }

    #[getter]
    fn enum_variants(&self) -> Vec<String> {
        self.enum_variants.clone()
    }

    #[getter]
    fn default_value(&self) -> Option<&str> {
        self.default_value.as_deref()
    }

    #[getter]
    fn validation_hint(&self) -> &str {
        &self.validation_hint
    }

    /// Get a summary dict for display purposes.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("field_name", &self.field_name)?;
        dict.set_item("display_name", &self.display_name)?;
        dict.set_item("field_type", &self.field_type)?;
        dict.set_item("section_id", &self.section_id)?;
        dict.set_item("is_required", self.is_required)?;
        dict.set_item("order", self.order)?;
        dict.set_item("suggestions", self.suggestions.clone())?;
        dict.set_item("enum_variants", self.enum_variants.clone())?;
        dict.set_item("default_value", self.default_value.clone())?;
        dict.set_item("validation_hint", &self.validation_hint)?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CompletionQuestion(field={:?}, type={}, required={}, section={:?})",
            self.field_name, self.field_type, self.is_required, self.section_id,
        )
    }
}
