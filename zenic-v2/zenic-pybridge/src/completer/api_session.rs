//! PyO3 API — Session management functions.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::catalog::catalog_get_by_id;
use crate::ingest::ExtractedText;

use super::types::*;
use super::validation::*;

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
