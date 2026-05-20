//! E2E Pipeline early stages: start, upload documents, get questions, submit answers.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::catalog::catalog_get_by_id;
use crate::completer::CompletionQuestion;

use super::types::{generate_pipeline_id, E2EPipelineStep, E2EPipelineState};

/// Start a new E2E pipeline by selecting a niche.
///
/// This is step 1 of the pipeline. It:
/// 1. Looks up the niche in the compiled catalog
/// 2. Generates a template skeleton
/// 3. Creates a CompletionSession
/// 4. Returns the pipeline state with template dict
///
/// Parameters
/// ----------
/// niche_id : str
///     The niche identifier from the catalog.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, dict or None]
///     (pipeline_state, template_dict) if niche found,
///     (pipeline_state, None) if niche not found.
#[pyfunction]
pub fn e2e_start(
    niche_id: &str,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, Option<Py<PyDict>>)> {
    let niche_id_trimmed = niche_id.trim();
    if niche_id_trimmed.is_empty() {
        let mut state = E2EPipelineState::new(
            "error".to_string(),
            "unknown".to_string(),
            "Unknown".to_string(),
            "unknown".to_string(),
            "low".to_string(),
            0,
            0,
        );
        state.add_error("niche_id cannot be empty".to_string());
        state.set_step(E2EPipelineStep::Error);
        return Ok((state, None));
    }

    let niche = match catalog_get_by_id(niche_id_trimmed) {
        Some(n) => n,
        None => {
            let mut state = E2EPipelineState::new(
                generate_pipeline_id(niche_id_trimmed),
                niche_id_trimmed.to_string(),
                "Unknown".to_string(),
                "unknown".to_string(),
                "low".to_string(),
                0,
                0,
            );
            state.add_error(format!("Niche '{}' not found in catalog", niche_id_trimmed));
            state.set_step(E2EPipelineStep::Error);
            return Ok((state, None));
        }
    };

    let pipeline_id = generate_pipeline_id(niche_id_trimmed);
    let total_fields = niche.total_field_count();
    let required_fields = niche.required_field_count();

    let mut state = E2EPipelineState::new(
        pipeline_id,
        niche.niche_id().to_string(),
        niche.name().to_string(),
        niche.category().as_str().to_string(),
        niche.data_sensitivity().as_str().to_string(),
        total_fields,
        required_fields,
    );

    // Generate template using Phase A function
    let template_dict = crate::template::template_generate(niche_id_trimmed, py);

    // Start completion session using Phase C function
    let (session, _) = crate::completer::completer_start_session(niche_id_trimmed, py)?;
    state.completion_session = Some(session);

    state.set_step(E2EPipelineStep::UploadDocuments);

    Ok((state, template_dict))
}

/// Upload and ingest documents into the pipeline.
///
/// This is step 2 of the pipeline. It:
/// 1. Processes uploaded documents through the ingestion pipeline
/// 2. Extracts field values using the extractor
/// 3. Auto-fills template fields
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// extracted_texts : list[ExtractedText]
///     Pre-extracted text objects from document ingestion.
///
/// Returns
/// -------
/// E2EPipelineState
///     Updated pipeline state.
#[pyfunction]
pub fn e2e_upload_documents(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    extracted_texts: &Bound<'_, PyList>,
    py: Python<'_>,
) -> PyResult<E2EPipelineState> {
    if let Some(ref mut session) = state.completion_session {
        let (updated_session, auto_filled) = crate::completer::completer_ingest_documents(
            session.clone(), template_dict, extracted_texts, py,
        )?;
        state.documents_ingested = updated_session.documents_ingested();
        *session = updated_session;
        state.fields_auto_filled = auto_filled;
    } else {
        state.add_error("No completion session — call e2e_start first".to_string());
    }

    state.set_step(E2EPipelineStep::GenerateQuestions);
    Ok(state)
}

/// Get questions for missing required fields.
///
/// This is step 3 of the pipeline. It generates structured
/// questions for all required fields that don't have values yet.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// template_dict : dict
///     The template dict.
///
/// Returns
/// -------
/// list[CompletionQuestion]
///     Structured questions for missing fields.
#[pyfunction]
pub fn e2e_get_questions(
    state: &E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<Vec<CompletionQuestion>> {
    match &state.completion_session {
        Some(session) => {
            crate::completer::completer_get_questions(session, template_dict, py)
        }
        None => Ok(Vec::new()),
    }
}

/// Submit a single answer for a missing field.
///
/// This is step 4 of the pipeline (single answer variant).
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// field_name : str
///     The field name to fill.
/// section_id : str
///     The section ID containing the field.
/// value : str
///     The value to set.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, bool]
///     (updated_state, was_applied).
#[pyfunction]
pub fn e2e_submit_answer(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    field_name: &str,
    section_id: &str,
    value: &str,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, bool)> {
    match &state.completion_session {
        Some(session) => {
            let (updated_session, _result_dict) = crate::completer::completer_submit_answer(
                session.clone(), template_dict, field_name, section_id, value, py,
            )?;
            let applied = true; // If no error, the answer was processed
            state.completion_session = Some(updated_session);
            if applied {
                state.fields_manual_filled += 1;
            }
            state.set_step(E2EPipelineStep::CollectAnswers);
            Ok((state, applied))
        }
        None => {
            state.add_error("No completion session".to_string());
            Ok((state, false))
        }
    }
}

/// Submit batch answers for missing fields.
///
/// This is step 4 of the pipeline (batch variant).
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// answers : dict[str, str]
///     Dict of field_name → value to set.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, int]
///     (updated_state, count_applied).
#[pyfunction]
pub fn e2e_submit_answers(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    answers: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, usize)> {
    match &state.completion_session {
        Some(session) => {
            // Convert PyDict answers to PyList of dicts for completer_submit_answers
            let answers_list = PyList::empty_bound(py);
            for (key, value) in answers.iter() {
                let field_name: String = key.extract()?;
                let field_value: String = value.extract()?;
                let entry = PyDict::new_bound(py);
                entry.set_item("field_name", field_name)?;
                entry.set_item("value", field_value)?;
                answers_list.append(entry.unbind())?;
            }

            let (updated_session, round) = crate::completer::completer_submit_answers(
                session.clone(), template_dict, &answers_list, py,
            )?;
            let count = round.answers_applied;
            state.completion_session = Some(updated_session);
            state.fields_manual_filled += count;
            state.set_step(E2EPipelineStep::CollectAnswers);
            Ok((state, count))
        }
        None => {
            state.add_error("No completion session".to_string());
            Ok((state, 0))
        }
    }
}
