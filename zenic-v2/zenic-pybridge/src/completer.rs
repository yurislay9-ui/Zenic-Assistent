//! Template Completion Agent for Zenic-Agents (Phase 6.C).
//!
//! Orchestrates the interactive template completion pipeline:
//! niche selection → template generation → document ingestion →
//! field extraction → auto-fill → interactive Q&A → finalization.
//!
//! # Architecture
//!
//! The completion agent ties together Fase A and Fase B:
//!
//! 1. User selects a niche → template_generate (Fase A)
//! 2. User uploads documents → ingest + extractor (Fase B)
//! 3. Auto-fill template from extracted data
//! 4. Identify missing required fields
//! 5. Generate structured questions for the user
//! 6. Validate and apply user answers
//! 7. Repeat 4-6 until all required fields are complete
//! 8. Finalize and export YAML template
//!
//! # Design Decisions
//!
//! - CompletionSession stores template_dict as a Python dict (Py<PyDict>)
//!   because template operations (set_field, validate, missing_fields)
//!   are all PyO3 functions that operate on PyDict.
//! - Session state is tracked via a session_id (UUID v4).
//! - Each Q&A round is tracked for audit purposes.
//! - No `unwrap` or `panic` — all errors handled explicitly.
//! - All external input is validated before processing.
//!
//! # PyO3 Exposed Types
//!
//! - `CompletionSession` — interactive template completion session
//! - `CompletionQuestion` — structured question for a missing field
//! - `CompletionRound` — one round of questions and answers
//! - `CompletionResult` — final result of the completion process
//!
//! # PyO3 Exposed Functions
//!
//! - `completer_start_session(niche_id)` — create new session
//! - `completer_ingest_documents(session, texts)` — ingest and auto-fill
//! - `completer_get_questions(session)` — get questions for missing fields
//! - `completer_submit_answer(session, field_name, value)` — process one answer
//! - `completer_submit_answers(session, answers)` — batch process answers
//! - `completer_validate_answer(field_type, value)` — validate a single answer
//! - `completer_get_progress(session)` — get completion progress
//! - `completer_is_complete(session)` — check if all required fields filled
//! - `completer_finalize(session)` — produce final YAML template
//! - `completer_get_field_suggestions(field_name, field_type)` — get suggestions

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde::{Deserialize, Serialize};

use crate::catalog::catalog_get_by_id;
use crate::ingest::ExtractedText;

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Maximum number of Q&A rounds before forcing finalization.
const MAX_ROUNDS: usize = 20;

/// Maximum number of questions returned per round.
const MAX_QUESTIONS_PER_ROUND: usize = 10;

/// Maximum answer length in characters.
const MAX_ANSWER_LENGTH: usize = 10000;

/// Minimum confidence for auto-accepted extraction matches.
const AUTO_ACCEPT_CONFIDENCE: f64 = 0.70;

/// Common suggestions per field type.
const SUGGESTIONS_BY_TYPE: &[(&str, &[&str])] = &[
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
const EMAIL_PATTERN: &str = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$";
const URL_PATTERN: &str = r"^https?://[a-zA-Z0-9.\-_/]+$";
const PHONE_PATTERN: &str = r"^[\+]?[\d\s\-\(\)]{7,20}$";
const DATE_PATTERN: &str = r"^\d{4}[-/]\d{2}[-/]\d{2}";
const DATETIME_PATTERN: &str = r"^\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}";

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
    session_id: String,
    niche_id: String,
    niche_name: String,
    category: String,
    data_sensitivity: String,
    round_count: usize,
    documents_ingested: usize,
    fields_auto_filled: usize,
    fields_manual_filled: usize,
    total_fields: usize,
    required_fields: usize,
    status: String,
    errors: Vec<String>,
    created_at: String,
    updated_at: String,
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
    field_name: String,
    display_name: String,
    field_type: String,
    section_id: String,
    description: String,
    is_required: bool,
    order: usize,
    suggestions: Vec<String>,
    enum_variants: Vec<String>,
    default_value: Option<String>,
    validation_hint: String,
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

// ═══════════════════════════════════════════════════════════════
//  CompletionRound — one round of questions and answers
// ═══════════════════════════════════════════════════════════════

/// One round of interactive Q&A in the completion process.
///
/// Tracks which questions were asked, which answers were
/// provided, and the result of applying each answer.
#[pyclass(name = "CompletionRound")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompletionRound {
    round_number: usize,
    questions_asked: usize,
    answers_received: usize,
    answers_applied: usize,
    answers_rejected: usize,
    still_missing: usize,
    completion_pct: f64,
}

#[pymethods]
impl CompletionRound {
    #[getter]
    fn round_number(&self) -> usize {
        self.round_number
    }

    #[getter]
    fn questions_asked(&self) -> usize {
        self.questions_asked
    }

    #[getter]
    fn answers_received(&self) -> usize {
        self.answers_received
    }

    #[getter]
    fn answers_applied(&self) -> usize {
        self.answers_applied
    }

    #[getter]
    fn answers_rejected(&self) -> usize {
        self.answers_rejected
    }

    #[getter]
    fn still_missing(&self) -> usize {
        self.still_missing
    }

    #[getter]
    fn completion_pct(&self) -> f64 {
        self.completion_pct
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("round_number", self.round_number)?;
        dict.set_item("questions_asked", self.questions_asked)?;
        dict.set_item("answers_received", self.answers_received)?;
        dict.set_item("answers_applied", self.answers_applied)?;
        dict.set_item("answers_rejected", self.answers_rejected)?;
        dict.set_item("still_missing", self.still_missing)?;
        dict.set_item("completion_pct", self.completion_pct)?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CompletionRound(round={}, asked={}, applied={}, rejected={}, missing={}, pct={:.1}%)",
            self.round_number,
            self.questions_asked,
            self.answers_applied,
            self.answers_rejected,
            self.still_missing,
            self.completion_pct,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  CompletionResult — final result of the completion process
// ═══════════════════════════════════════════════════════════════

/// Final result of the template completion process.
///
/// Contains the completed template, statistics, and any
/// warnings or errors from the entire process.
#[pyclass(name = "CompletionResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompletionResult {
    session_id: String,
    niche_id: String,
    status: String,
    total_fields: usize,
    filled_fields: usize,
    missing_optional: usize,
    completion_pct: f64,
    total_rounds: usize,
    auto_filled: usize,
    manual_filled: usize,
    documents_used: usize,
    warnings: Vec<String>,
    errors: Vec<String>,
}

#[pymethods]
impl CompletionResult {
    #[getter]
    fn session_id(&self) -> &str {
        &self.session_id
    }

    #[getter]
    fn niche_id(&self) -> &str {
        &self.niche_id
    }

    #[getter]
    fn status(&self) -> &str {
        &self.status
    }

    #[getter]
    fn total_fields(&self) -> usize {
        self.total_fields
    }

    #[getter]
    fn filled_fields(&self) -> usize {
        self.filled_fields
    }

    #[getter]
    fn missing_optional(&self) -> usize {
        self.missing_optional
    }

    #[getter]
    fn completion_pct(&self) -> f64 {
        self.completion_pct
    }

    #[getter]
    fn total_rounds(&self) -> usize {
        self.total_rounds
    }

    #[getter]
    fn auto_filled(&self) -> usize {
        self.auto_filled
    }

    #[getter]
    fn manual_filled(&self) -> usize {
        self.manual_filled
    }

    #[getter]
    fn documents_used(&self) -> usize {
        self.documents_used
    }

    #[getter]
    fn warnings(&self) -> Vec<String> {
        self.warnings.clone()
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    #[getter]
    fn is_complete(&self) -> bool {
        self.status == "complete"
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("session_id", &self.session_id)?;
        dict.set_item("niche_id", &self.niche_id)?;
        dict.set_item("status", &self.status)?;
        dict.set_item("total_fields", self.total_fields)?;
        dict.set_item("filled_fields", self.filled_fields)?;
        dict.set_item("missing_optional", self.missing_optional)?;
        dict.set_item("completion_pct", self.completion_pct)?;
        dict.set_item("total_rounds", self.total_rounds)?;
        dict.set_item("auto_filled", self.auto_filled)?;
        dict.set_item("manual_filled", self.manual_filled)?;
        dict.set_item("documents_used", self.documents_used)?;
        dict.set_item("is_complete", self.is_complete())?;
        dict.set_item("warning_count", self.warnings.len())?;
        dict.set_item("error_count", self.errors.len())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CompletionResult(session={:?}, niche={:?}, status={}, pct={:.1}%)",
            self.session_id, self.niche_id, self.status, self.completion_pct,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers — Validation
// ═══════════════════════════════════════════════════════════════

/// Validate a value against a field type.
///
/// Returns (is_valid, error_message).
fn validate_value_for_type(field_type: &str, value: &str) -> (bool, Option<String>) {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return (false, Some("Value cannot be empty".to_string()));
    }

    match field_type {
        "email" => {
            let re = regex::Regex::new(EMAIL_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid email format: {}", trimmed)))
                    }
                }
                Err(_) => {
                    // Fallback: basic check
                    if trimmed.contains('@') && trimmed.contains('.') {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid email format: {}", trimmed)))
                    }
                }
            }
        }
        "url" => {
            let re = regex::Regex::new(URL_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else if trimmed.contains('.') && !trimmed.contains(' ') {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid URL format: {}", trimmed)))
                    }
                }
                Err(_) => {
                    if trimmed.starts_with("http") || trimmed.contains('.') {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid URL format: {}", trimmed)))
                    }
                }
            }
        }
        "phone" => {
            let re = regex::Regex::new(PHONE_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                        if digit_count >= 7 {
                            (true, None)
                        } else {
                            (false, Some(format!("Invalid phone format: {}", trimmed)))
                        }
                    }
                }
                Err(_) => {
                    let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                    if digit_count >= 7 {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid phone format: {}", trimmed)))
                    }
                }
            }
        }
        "number" => {
            if trimmed.parse::<f64>().is_ok() {
                (true, None)
            } else {
                (false, Some(format!("Invalid number: {}", trimmed)))
            }
        }
        "currency" => {
            let cleaned: String = trimmed
                .chars()
                .filter(|c| c.is_ascii_digit() || *c == '.' || *c == '-' || *c == ',')
                .collect();
            let normalized = cleaned.replace(',', "");
            if normalized.parse::<f64>().is_ok() {
                (true, None)
            } else {
                (false, Some(format!("Invalid currency value: {}", trimmed)))
            }
        }
        "percentage" => {
            let cleaned: String = trimmed.trim_end_matches('%').trim().to_string();
            if cleaned.parse::<f64>().is_ok() {
                (true, None)
            } else {
                (false, Some(format!("Invalid percentage: {}", trimmed)))
            }
        }
        "boolean" => {
            let lower = trimmed.to_lowercase();
            if matches!(lower.as_str(), "true" | "false" | "yes" | "no" | "1" | "0" | "si")
            {
                (true, None)
            } else {
                (false, Some(format!("Invalid boolean: {} (use true/false)", trimmed)))
            }
        }
        "date" => {
            let re = regex::Regex::new(DATE_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid date format (use YYYY-MM-DD): {}", trimmed)))
                    }
                }
                Err(_) => {
                    let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                    if digit_count >= 4 {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid date format: {}", trimmed)))
                    }
                }
            }
        }
        "datetime" => {
            let re = regex::Regex::new(DATETIME_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid datetime format (use ISO 8601): {}", trimmed)))
                    }
                }
                Err(_) => {
                    let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                    if digit_count >= 8 {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid datetime format: {}", trimmed)))
                    }
                }
            }
        }
        "json" => {
            if trimmed.starts_with('{') || trimmed.starts_with('[') {
                match serde_json::from_str::<serde_json::Value>(trimmed) {
                    Ok(_) => (true, None),
                    Err(e) => (false, Some(format!("Invalid JSON: {}", e))),
                }
            } else {
                (false, Some("JSON must start with { or [".to_string()))
            }
        }
        "enum" => {
            // Enum validation is context-dependent; accept any non-empty value
            (true, None)
        }
        "reference" => {
            // Reference validation is context-dependent; accept any non-empty value
            (true, None)
        }
        "file" => {
            // File validation is context-dependent; accept any non-empty value
            (true, None)
        }
        _ => {
            // "text" and unknown types: accept any non-empty value
            (true, None)
        }
    }
}

/// Get the validation hint for a field type.
fn validation_hint_for_type(field_type: &str) -> String {
    match field_type {
        "email" => "Enter a valid email address (e.g., user@example.com)".to_string(),
        "url" => "Enter a valid URL (e.g., https://example.com)".to_string(),
        "phone" => "Enter a phone number with at least 7 digits".to_string(),
        "number" => "Enter a numeric value".to_string(),
        "currency" => "Enter a monetary value (e.g., 1000.00)".to_string(),
        "percentage" => "Enter a percentage (e.g., 15 or 15%)".to_string(),
        "boolean" => "Enter true or false (or yes/no)".to_string(),
        "date" => "Enter a date in YYYY-MM-DD format".to_string(),
        "datetime" => "Enter a datetime in ISO 8601 format".to_string(),
        "json" => "Enter a valid JSON object or array".to_string(),
        "enum" => "Select one of the available options".to_string(),
        "reference" => "Enter the identifier of the referenced entity".to_string(),
        "file" => "Provide a file path or upload a file".to_string(),
        _ => "Enter a text value".to_string(),
    }
}

/// Get suggestions for a field by name and type.
fn get_suggestions_for_field(field_name: &str, field_type: &str) -> Vec<String> {
    // Check field-specific suggestions
    let name_lower = field_name.to_lowercase();
    for (key, suggestions) in SUGGESTIONS_BY_TYPE {
        if *key == name_lower {
            return suggestions.iter().map(|s| s.to_string()).collect();
        }
    }

    // Fall back to type-based suggestions
    match field_type {
        "boolean" => vec!["true".to_string(), "false".to_string()],
        "enum" => vec![], // Enum variants are provided by the template
        _ => vec![],
    }
}

/// Generate a simple UUID-like session ID.
fn generate_session_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("{:016x}-{:04x}", timestamp, (timestamp % 65536) as u16)
}

/// Sanitize a string value for template insertion.
fn sanitize_value(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.len() > MAX_ANSWER_LENGTH {
        trimmed.chars().take(MAX_ANSWER_LENGTH).collect()
    } else {
        trimmed.to_string()
    }
}

/// Get the field type for a field in the template.
fn get_field_type_from_template(
    template_dict: &Bound<'_, PyDict>,
    section_id: &str,
    field_name: &str,
) -> String {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return "text".to_string(),
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return "text".to_string(),
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    let section_val = match sections.get_item(section_id) {
        Ok(Some(v)) => v,
        _ => return "text".to_string(),
    };

    let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    let field_val = match section_dict.get_item(field_name) {
        Ok(Some(v)) => v,
        _ => return "text".to_string(),
    };

    let field_dict: &Bound<'_, PyDict> = match field_val.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    field_dict
        .get_item("_type")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or_else(|| "text".to_string())
}

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Public API
// ═══════════════════════════════════════════════════════════════

/// Start a new template completion session.
///
/// Creates a CompletionSession and generates the initial
/// template skeleton from the specified niche.
///
/// Parameters
/// ----------
/// niche_id : str
///     The niche identifier from the catalog (e.g., ``"telemedicine"``).
///
/// Returns
/// -------
/// tuple[CompletionSession, dict]
///     A tuple of (session, template_dict) if the niche exists,
///     or (session, None) if the niche is not found.
///     The session is always created but may have errors.
#[pyfunction]
pub fn completer_start_session(
    niche_id: &str,
    py: Python<'_>,
) -> PyResult<(CompletionSession, Option<Py<PyDict>>)> {
    let niche_id_trimmed = niche_id.trim();
    if niche_id_trimmed.is_empty() {
        let mut session = CompletionSession::new(
            generate_session_id(),
            "unknown".to_string(),
            "Unknown".to_string(),
            "unknown".to_string(),
            "low".to_string(),
            0,
            0,
        );
        session.add_error("niche_id cannot be empty".to_string());
        session.set_status("error");
        return Ok((session, None));
    }

    let niche = match catalog_get_by_id(niche_id_trimmed) {
        Some(n) => n,
        None => {
            let mut session = CompletionSession::new(
                generate_session_id(),
                niche_id_trimmed.to_string(),
                "Unknown".to_string(),
                "unknown".to_string(),
                "low".to_string(),
                0,
                0,
            );
            session.add_error(format!("Niche '{}' not found in catalog", niche_id_trimmed));
            session.set_status("error");
            return Ok((session, None));
        }
    };

    let total_fields = niche.total_field_count();
    let required_fields = niche.required_field_count();

    let session = CompletionSession::new(
        generate_session_id(),
        niche.niche_id().to_string(),
        niche.name().to_string(),
        niche.category().as_str().to_string(),
        niche.data_sensitivity().as_str().to_string(),
        total_fields,
        required_fields,
    );

    // Generate the template using the Fase A function
    let template_dict = crate::template::template_generate(niche_id_trimmed, py);

    Ok((session, template_dict))
}

/// Ingest documents and auto-fill template fields.
///
/// Takes an existing session and template, processes the
/// provided documents, extracts fields, and applies matches
/// to the template. Uses the Fase B extractor pipeline.
///
/// Parameters
/// ----------
/// session : CompletionSession
///     The current completion session (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// extracted_texts : list[ExtractedText]
///     List of ExtractedText objects from document ingestion.
///
/// Returns
/// -------
/// tuple[CompletionSession, int]
///     Updated (session, fields_auto_filled) tuple.
#[pyfunction]
pub fn completer_ingest_documents(
    mut session: CompletionSession,
    template_dict: &Bound<'_, PyDict>,
    extracted_texts: &Bound<'_, PyList>,
    py: Python<'_>,
) -> PyResult<(CompletionSession, usize)> {
    let texts: Vec<ExtractedText> = match extracted_texts.extract() {
        Ok(t) => t,
        Err(e) => {
            session.add_error(format!("Invalid extracted_texts parameter: {}", e));
            return Ok((session, 0));
        }
    };

    if texts.is_empty() {
        session.add_error("No documents provided for ingestion".to_string());
        return Ok((session, 0));
    }

    // Count valid (non-empty) documents
    let valid_count = texts.iter().filter(|t| !t.is_empty()).count();
    session.add_documents(valid_count);

    if valid_count == 0 {
        session.add_error("All provided documents are empty".to_string());
        return Ok((session, 0));
    }

    // Use Fase B extractor to match fields
    let extraction_result = crate::extractor::extractor_match_fields(
        template_dict,
        extracted_texts,
        py,
    )?;

    // Apply matches to the template using Fase B extractor
    let matches_list = PyList::empty_bound(py);
    for field_match in extraction_result.matches() {
        if field_match.confidence() >= AUTO_ACCEPT_CONFIDENCE {
            matches_list.append(field_match.clone())?;
        }
    }

    let auto_count = matches_list.len();

    let applied = crate::extractor::extractor_apply_matches(
        template_dict,
        &matches_list,
    )?;

    let auto_filled = if applied { auto_count } else { 0 };
    session.add_auto_filled(auto_filled);
    session.set_status("documents_ingested");

    Ok((session, auto_filled))
}

/// Get questions for all missing required fields.
///
/// Analyzes the template and generates structured questions
/// for each required field that does not yet have a value.
/// This is the primary function for the interactive Q&A loop.
///
/// Parameters
/// ----------
/// session : CompletionSession
///     The current completion session.
/// template_dict : dict
///     The template dict to analyze.
///
/// Returns
/// -------
/// list[CompletionQuestion]
///     Structured questions for missing required fields,
///     ordered by section and field order. Limited to
///     MAX_QUESTIONS_PER_ROUND per call.
#[pyfunction]
pub fn completer_get_questions(
    session: &CompletionSession,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<Vec<CompletionQuestion>> {
    if session.round_count >= MAX_ROUNDS {
        return Ok(Vec::new());
    }

    // Use Fase A template_missing_fields to get missing fields
    let missing_fields = crate::template::template_missing_fields(template_dict, py)?;

    let mut questions: Vec<CompletionQuestion> = Vec::new();

    for field_info_py in &missing_fields {
        let field_info = field_info_py.bind(py);

        let field_name: String = field_info
            .get_item("name")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or_default();

        let display_name: String = field_info
            .get_item("display_name")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or_else(|| field_name.clone());

        let field_type: String = field_info
            .get_item("type")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or_else(|| "text".to_string());

        let section_id: String = field_info
            .get_item("section")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or_default();

        let description: String = field_info
            .get_item("description")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or_default();

        if field_name.is_empty() {
            continue;
        }

        let mut question = CompletionQuestion::new(
            field_name,
            display_name,
            field_type.clone(),
            section_id,
        );
        question.description = description;
        question.is_required = true;
        question.validation_hint = validation_hint_for_type(&field_type);
        question.suggestions = get_suggestions_for_field(
            &question.field_name,
            &field_type,
        );

        // Extract enum variants if present
        let enum_variants: Vec<String> = field_info
            .get_item("enum_variants")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or_default();
        question.enum_variants = enum_variants;

        questions.push(question);

        if questions.len() >= MAX_QUESTIONS_PER_ROUND {
            break;
        }
    }

    Ok(questions)
}

/// Submit a single answer for a missing field.
///
/// Validates the answer against the field type, and if valid,
/// applies it to the template. Returns the validation result
/// and whether the answer was applied.
///
/// Parameters
/// ----------
/// session : CompletionSession
///     The current completion session (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// field_name : str
///     The field name to fill.
/// section_id : str
///     The section containing the field.
/// value : str
///     The user's answer.
///
/// Returns
/// -------
/// tuple[CompletionSession, dict]
///     Updated (session, result_dict) where result_dict contains:
///     - ``applied`` (bool): Whether the answer was applied
///     - ``valid`` (bool): Whether the value is valid for the type
///     - ``error`` (str, optional): Error message if invalid
#[pyfunction]
#[pyo3(signature = (session, template_dict, field_name, section_id, value))]
pub fn completer_submit_answer(
    mut session: CompletionSession,
    template_dict: &Bound<'_, PyDict>,
    field_name: &str,
    section_id: &str,
    value: &str,
    py: Python<'_>,
) -> PyResult<(CompletionSession, Py<PyDict>)> {
    let result_dict = PyDict::new_bound(py);

    // Validate inputs
    let field_name_trimmed = field_name.trim();
    let section_id_trimmed = section_id.trim();
    let value_sanitized = sanitize_value(value);

    if field_name_trimmed.is_empty() {
        result_dict.set_item("applied", false)?;
        result_dict.set_item("valid", false)?;
        result_dict.set_item("error", "field_name cannot be empty")?;
        return Ok((session, result_dict.unbind()));
    }

    if section_id_trimmed.is_empty() {
        result_dict.set_item("applied", false)?;
        result_dict.set_item("valid", false)?;
        result_dict.set_item("error", "section_id cannot be empty")?;
        return Ok((session, result_dict.unbind()));
    }

    if value_sanitized.is_empty() {
        result_dict.set_item("applied", false)?;
        result_dict.set_item("valid", false)?;
        result_dict.set_item("error", "value cannot be empty")?;
        return Ok((session, result_dict.unbind()));
    }

    // Determine the field type from the template
    let field_type = get_field_type_from_template(template_dict, section_id_trimmed, field_name_trimmed);

    // Validate the value
    let (is_valid, validation_error) = validate_value_for_type(
        &field_type,
        &value_sanitized,
    );

    result_dict.set_item("valid", is_valid)?;

    if !is_valid {
        let err_msg = validation_error.unwrap_or_else(|| "Validation failed".to_string());
        result_dict.set_item("applied", false)?;
        result_dict.set_item("error", err_msg)?;
        session.add_error(format!(
            "Invalid answer for field '{}': {}",
            field_name_trimmed, value_sanitized
        ));
        return Ok((session, result_dict.unbind()));
    }

    // Apply the answer using Fase A template_set_field
    let applied = crate::template::template_set_field(
        template_dict,
        section_id_trimmed,
        field_name_trimmed,
        value_sanitized.as_str().into(),
    )?;

    result_dict.set_item("applied", applied)?;

    if applied {
        session.add_manual_filled(1);
        session.set_status("in_progress");
    } else {
        result_dict.set_item("error", "Field not found in template")?;
        session.add_error(format!(
            "Field '{}' not found in section '{}'",
            field_name_trimmed, section_id_trimmed
        ));
    }

    Ok((session, result_dict.unbind()))
}

/// Submit multiple answers at once.
///
/// Processes a batch of field answers, validating each one
/// and applying valid answers to the template. Returns a
/// summary of the round.
///
/// Parameters
/// ----------
/// session : CompletionSession
///     The current completion session (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// answers : list[dict]
///     List of answer dicts, each with keys:
///     - ``field_name`` (str): The field name
///     - ``section_id`` (str): The section ID
///     - ``value`` (str): The user's answer
///
/// Returns
/// -------
/// tuple[CompletionSession, CompletionRound]
///     Updated (session, round_result) tuple.
#[pyfunction]
pub fn completer_submit_answers(
    mut session: CompletionSession,
    template_dict: &Bound<'_, PyDict>,
    answers: &Bound<'_, PyList>,
    py: Python<'_>,
) -> PyResult<(CompletionSession, CompletionRound)> {
    session.increment_round();

    let answers_count = answers.len();
    let mut applied_count: usize = 0;
    let mut rejected_count: usize = 0;

    for item in answers.iter() {
        let field_name: String = match item.get_item("field_name") {
            Ok(Some(v)) => match v.extract() {
                Ok(s) => s,
                Err(_) => {
                    rejected_count += 1;
                    continue;
                }
            },
            _ => {
                rejected_count += 1;
                continue;
            }
        };

        let section_id: String = match item.get_item("section_id") {
            Ok(Some(v)) => match v.extract() {
                Ok(s) => s,
                Err(_) => {
                    rejected_count += 1;
                    continue;
                }
            },
            _ => {
                rejected_count += 1;
                continue;
            }
        };

        let value: String = match item.get_item("value") {
            Ok(Some(v)) => match v.extract() {
                Ok(s) => s,
                Err(_) => {
                    rejected_count += 1;
                    continue;
                }
            },
            _ => {
                rejected_count += 1;
                continue;
            }
        };

        let (updated_session, result) = completer_submit_answer(
            session,
            template_dict,
            &field_name,
            &section_id,
            &value,
            py,
        )?;
        session = updated_session;

        let was_applied: bool = result
            .bind(py)
            .get_item("applied")
            .ok()
            .flatten()
            .and_then(|v| v.extract().ok())
            .unwrap_or(false);

        if was_applied {
            applied_count += 1;
        } else {
            rejected_count += 1;
        }
    }

    // Calculate current progress
    let validation = crate::template::template_validate(template_dict, py)?;
    let validation_bound = validation.bind(py);
    let still_missing: usize = validation_bound
        .get_item("missing_required")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);
    let completion_pct: f64 = validation_bound
        .get_item("completion_pct")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0.0);

    if still_missing == 0 {
        session.set_status("complete");
    } else {
        session.set_status("in_progress");
    }

    let round = CompletionRound {
        round_number: session.round_count,
        questions_asked: answers_count,
        answers_received: answers_count,
        answers_applied: applied_count,
        answers_rejected: rejected_count,
        still_missing,
        completion_pct,
    };

    Ok((session, round))
}

/// Validate a single answer against a field type.
///
/// Does not modify the template; only checks if the value
/// is valid for the specified field type.
///
/// Parameters
/// ----------
/// field_type : str
///     The field type (e.g., ``"email"``, ``"number"``).
/// value : str
///     The value to validate.
///
/// Returns
/// -------
/// dict
///     Validation result with keys:
///     - ``valid`` (bool): Whether the value is valid
///     - ``error`` (str, optional): Error message if invalid
///     - ``sanitized`` (str): The sanitized value
#[pyfunction]
pub fn completer_validate_answer(
    field_type: &str,
    value: &str,
    py: Python<'_>,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    let field_type_trimmed = field_type.trim();
    let value_sanitized = sanitize_value(value);

    if value_sanitized.is_empty() {
        result.set_item("valid", false)?;
        result.set_item("error", "Value cannot be empty")?;
        result.set_item("sanitized", "")?;
        return Ok(result.unbind());
    }

    let (is_valid, validation_error) = validate_value_for_type(
        field_type_trimmed,
        &value_sanitized,
    );

    result.set_item("valid", is_valid)?;
    result.set_item("sanitized", &value_sanitized)?;

    if let Some(err) = validation_error {
        result.set_item("error", err)?;
    }

    Ok(result.unbind())
}

/// Get current completion progress.
///
/// Returns detailed progress information about the template
/// completion, including per-section statistics.
///
/// Parameters
/// ----------
/// session : CompletionSession
///     The current completion session.
/// template_dict : dict
///     The template dict to analyze.
///
/// Returns
/// -------
/// dict
///     Progress information with keys:
///     - ``total_fields`` (int): Total field count
///     - ``filled_fields`` (int): Fields with values
///     - ``missing_required`` (int): Required fields without values
///     - ``missing_optional`` (int): Optional fields without values
///     - ``completion_pct`` (float): Overall completion percentage
///     - ``required_pct`` (float): Required fields completion percentage
///     - ``status`` (str): "complete", "partial", or "incomplete"
///     - ``auto_filled`` (int): Fields auto-filled from documents
///     - ``manual_filled`` (int): Fields manually filled by user
///     - ``rounds`` (int): Number of Q&A rounds completed
#[pyfunction]
pub fn completer_get_progress(
    session: &CompletionSession,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    let validation = crate::template::template_validate(template_dict, py)?;
    let vb = validation.bind(py);

    let total_fields: usize = vb
        .get_item("total_fields")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    let filled_fields: usize = vb
        .get_item("filled_fields")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    let missing_required: usize = vb
        .get_item("missing_required")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    let completion_pct: f64 = vb
        .get_item("completion_pct")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0.0);

    let status: String = vb
        .get_item("status")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or_else(|| "unknown".to_string());

    let required_fields = session.required_fields;
    let required_filled = required_fields.saturating_sub(missing_required);
    let required_pct = if required_fields > 0 {
        (required_filled as f64 / required_fields as f64) * 100.0
    } else {
        100.0
    };

    let missing_optional = total_fields
        .saturating_sub(filled_fields)
        .saturating_sub(missing_required);

    result.set_item("total_fields", total_fields)?;
    result.set_item("filled_fields", filled_fields)?;
    result.set_item("missing_required", missing_required)?;
    result.set_item("missing_optional", missing_optional)?;
    result.set_item("completion_pct", completion_pct)?;
    result.set_item("required_pct", required_pct)?;
    result.set_item("status", &status)?;
    result.set_item("auto_filled", session.fields_auto_filled)?;
    result.set_item("manual_filled", session.fields_manual_filled)?;
    result.set_item("rounds", session.round_count)?;
    result.set_item("documents_ingested", session.documents_ingested)?;

    Ok(result.unbind())
}

/// Check if all required fields are complete.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict to check.
///
/// Returns
/// -------
/// bool
///     True if all required fields have values.
#[pyfunction]
pub fn completer_is_complete(
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<bool> {
    let validation = crate::template::template_validate(template_dict, py)?;
    let vb = validation.bind(py);
    let missing_required: usize = vb
        .get_item("missing_required")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(1);
    Ok(missing_required == 0)
}

/// Finalize the template completion process.
///
/// Validates the final template, generates the YAML output,
/// and returns a CompletionResult with all statistics.
///
/// Parameters
/// ----------
/// session : CompletionSession
///     The current completion session.
/// template_dict : dict
///     The completed template dict.
///
/// Returns
/// -------
/// tuple[CompletionResult, str]
///     (result, yaml_string) tuple. The YAML string is the
///     serialized template. If there are missing required fields,
///     warnings will be included in the result.
#[pyfunction]
pub fn completer_finalize(
    session: &CompletionSession,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(CompletionResult, String)> {
    let validation = crate::template::template_validate(template_dict, py)?;
    let vb = validation.bind(py);

    let total_fields: usize = vb
        .get_item("total_fields")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    let filled_fields: usize = vb
        .get_item("filled_fields")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    let missing_required: usize = vb
        .get_item("missing_required")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0);

    let completion_pct: f64 = vb
        .get_item("completion_pct")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(0.0);

    let valid: bool = vb
        .get_item("valid")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or(false);

    let missing_optional = total_fields
        .saturating_sub(filled_fields)
        .saturating_sub(missing_required);

    let status = if valid {
        "complete".to_string()
    } else if filled_fields > 0 {
        "partial".to_string()
    } else {
        "incomplete".to_string()
    };

    let mut warnings: Vec<String> = Vec::new();
    if missing_required > 0 {
        warnings.push(format!(
            "Template finalized with {} missing required fields",
            missing_required
        ));
    }
    if missing_optional > 0 {
        warnings.push(format!(
            "{} optional fields remain unfilled",
            missing_optional
        ));
    }

    // Generate YAML using Fase A function
    let yaml_string = crate::template::template_to_yaml(template_dict, py)?;

    let result = CompletionResult {
        session_id: session.session_id.clone(),
        niche_id: session.niche_id.clone(),
        status,
        total_fields,
        filled_fields,
        missing_optional,
        completion_pct,
        total_rounds: session.round_count,
        auto_filled: session.fields_auto_filled,
        manual_filled: session.fields_manual_filled,
        documents_used: session.documents_ingested,
        warnings,
        errors: session.errors.clone(),
    };

    Ok((result, yaml_string))
}

/// Get suggestions for a template field.
///
/// Returns suggested values based on the field name and type.
/// Useful for providing autocomplete or dropdown options in
/// the frontend.
///
/// Parameters
/// ----------
/// field_name : str
///     The field name (e.g., ``"auth_method"``).
/// field_type : str
///     The field type (e.g., ``"enum"``).
///
/// Returns
/// -------
/// list[str]
///     Suggested values for the field.
#[pyfunction]
pub fn completer_get_field_suggestions(
    field_name: &str,
    field_type: &str,
) -> Vec<String> {
    get_suggestions_for_field(field_name.trim(), field_type.trim())
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_completion_session_creation() {
        let session = CompletionSession::new(
            "test-session-001".to_string(),
            "telemedicine".to_string(),
            "Telemedicine".to_string(),
            "healthtech".to_string(),
            "critical".to_string(),
            45,
            30,
        );
        assert_eq!(session.session_id(), "test-session-001");
        assert_eq!(session.niche_id(), "telemedicine");
        assert_eq!(session.category(), "healthtech");
        assert_eq!(session.total_fields(), 45);
        assert_eq!(session.required_fields(), 30);
        assert_eq!(session.round_count(), 0);
        assert_eq!(session.status(), "initialized");
    }

    #[test]
    fn test_completion_session_tracking() {
        let mut session = CompletionSession::new(
            "test-session-002".to_string(),
            "ai_automation".to_string(),
            "AI Automation".to_string(),
            "ai_data".to_string(),
            "high".to_string(),
            30,
            20,
        );
        session.add_documents(3);
        session.add_auto_filled(12);
        session.add_manual_filled(5);
        session.increment_round();
        session.set_status("in_progress");
        assert_eq!(session.documents_ingested(), 3);
        assert_eq!(session.fields_auto_filled(), 12);
        assert_eq!(session.fields_manual_filled(), 5);
        assert_eq!(session.round_count(), 1);
        assert_eq!(session.status(), "in_progress");
    }

    #[test]
    fn test_completion_question_creation() {
        let question = CompletionQuestion::new(
            "business_name".to_string(),
            "Business Name".to_string(),
            "text".to_string(),
            "business_identity".to_string(),
        );
        assert_eq!(question.field_name(), "business_name");
        assert_eq!(question.display_name(), "Business Name");
        assert_eq!(question.field_type(), "text");
        assert_eq!(question.section_id(), "business_identity");
        assert!(question.is_required);
    }

    #[test]
    fn test_validate_value_email() {
        let (valid, _) = validate_value_for_type("email", "user@example.com");
        assert!(valid);
        let (valid, _) = validate_value_for_type("email", "not-an-email");
        assert!(!valid);
        let (valid, _) = validate_value_for_type("email", "");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_url() {
        let (valid, _) = validate_value_for_type("url", "https://example.com");
        assert!(valid);
    }

    #[test]
    fn test_validate_value_number() {
        let (valid, _) = validate_value_for_type("number", "42");
        assert!(valid);
        let (valid, _) = validate_value_for_type("number", "3.14");
        assert!(valid);
        let (valid, _) = validate_value_for_type("number", "not-a-number");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_boolean() {
        let (valid, _) = validate_value_for_type("boolean", "true");
        assert!(valid);
        let (valid, _) = validate_value_for_type("boolean", "false");
        assert!(valid);
        let (valid, _) = validate_value_for_type("boolean", "yes");
        assert!(valid);
        let (valid, _) = validate_value_for_type("boolean", "maybe");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_percentage() {
        let (valid, _) = validate_value_for_type("percentage", "15");
        assert!(valid);
        let (valid, _) = validate_value_for_type("percentage", "15%");
        assert!(valid);
        let (valid, _) = validate_value_for_type("percentage", "not-a-pct");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_currency() {
        let (valid, _) = validate_value_for_type("currency", "1000.00");
        assert!(valid);
        let (valid, _) = validate_value_for_type("currency", "$1,000.00");
        assert!(valid);
    }

    #[test]
    fn test_validate_value_json() {
        let (valid, _) = validate_value_for_type("json", "{\"key\": \"value\"}");
        assert!(valid);
        let (valid, _) = validate_value_for_type("json", "[1, 2, 3]");
        assert!(valid);
        let (valid, _) = validate_value_for_type("json", "not json");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_date() {
        let (valid, _) = validate_value_for_type("date", "2025-01-15");
        assert!(valid);
    }

    #[test]
    fn test_validate_value_text() {
        let (valid, _) = validate_value_for_type("text", "Any text value");
        assert!(valid);
        let (valid, _) = validate_value_for_type("text", "");
        assert!(!valid);
    }

    #[test]
    fn test_validation_hint_for_type() {
        assert!(validation_hint_for_type("email").contains("email"));
        assert!(validation_hint_for_type("url").contains("URL"));
        assert!(validation_hint_for_type("boolean").contains("true"));
        assert!(validation_hint_for_type("number").contains("numeric"));
    }

    #[test]
    fn test_get_suggestions_for_field() {
        let suggestions = get_suggestions_for_field("auth_method", "enum");
        assert!(!suggestions.is_empty());
        assert!(suggestions.contains(&"oauth2".to_string()));

        let suggestions = get_suggestions_for_field("base_currency", "currency");
        assert!(!suggestions.is_empty());
        assert!(suggestions.contains(&"USD".to_string()));

        let suggestions = get_suggestions_for_field("unknown_field", "text");
        assert!(suggestions.is_empty());
    }

    #[test]
    fn test_sanitize_value() {
        assert_eq!(sanitize_value("  hello  "), "hello");
        assert_eq!(sanitize_value("normal text"), "normal text");
        // Test truncation
        let long_value = "a".repeat(MAX_ANSWER_LENGTH + 100);
        let sanitized = sanitize_value(&long_value);
        assert_eq!(sanitized.len(), MAX_ANSWER_LENGTH);
    }

    #[test]
    fn test_generate_session_id() {
        let id1 = generate_session_id();
        let id2 = generate_session_id();
        assert!(!id1.is_empty());
        assert!(!id2.is_empty());
        // IDs should be unique (at least different with high probability)
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_completion_result_creation() {
        let result = CompletionResult {
            session_id: "test-session-003".to_string(),
            niche_id: "telemedicine".to_string(),
            status: "complete".to_string(),
            total_fields: 45,
            filled_fields: 45,
            missing_optional: 0,
            completion_pct: 100.0,
            total_rounds: 3,
            auto_filled: 20,
            manual_filled: 25,
            documents_used: 2,
            warnings: Vec::new(),
            errors: Vec::new(),
        };
        assert_eq!(result.session_id(), "test-session-003");
        assert_eq!(result.niche_id(), "telemedicine");
        assert!(result.is_complete());
        assert_eq!(result.auto_filled(), 20);
        assert_eq!(result.manual_filled(), 25);
    }

    #[test]
    fn test_completion_result_partial() {
        let result = CompletionResult {
            session_id: "test-session-004".to_string(),
            niche_id: "ai_automation".to_string(),
            status: "partial".to_string(),
            total_fields: 30,
            filled_fields: 25,
            missing_optional: 5,
            completion_pct: 83.3,
            total_rounds: 2,
            auto_filled: 15,
            manual_filled: 10,
            documents_used: 1,
            warnings: vec!["5 optional fields remain unfilled".to_string()],
            errors: Vec::new(),
        };
        assert!(!result.is_complete());
        assert_eq!(result.warnings().len(), 1);
    }

    #[test]
    fn test_completion_round() {
        let round = CompletionRound {
            round_number: 1,
            questions_asked: 10,
            answers_received: 8,
            answers_applied: 7,
            answers_rejected: 1,
            still_missing: 3,
            completion_pct: 75.0,
        };
        assert_eq!(round.round_number(), 1);
        assert_eq!(round.questions_asked(), 10);
        assert_eq!(round.answers_applied(), 7);
        assert_eq!(round.still_missing(), 3);
    }

    #[test]
    fn test_max_rounds_constant() {
        assert_eq!(MAX_ROUNDS, 20);
    }

    #[test]
    fn test_max_questions_per_round_constant() {
        assert_eq!(MAX_QUESTIONS_PER_ROUND, 10);
    }

    #[test]
    fn test_auto_accept_confidence_constant() {
        assert!((AUTO_ACCEPT_CONFIDENCE - 0.70).abs() < 0.001);
    }
}
