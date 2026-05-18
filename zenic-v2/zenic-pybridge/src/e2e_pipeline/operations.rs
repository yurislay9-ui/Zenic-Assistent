//! E2E Pipeline — PyO3 function implementations (public API) + helpers.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::catalog::catalog_get_by_id;
use crate::completer::{
    CompletionQuestion, CompletionSession,
};
use crate::safety_gate_extended::{ComplianceCheckResult, DomainSafetyCheckResult};

use super::types::{E2EPipelineState, E2EPipelineStep};

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers
// ═══════════════════════════════════════════════════════════════

/// Generate a pipeline ID.
pub(crate) fn generate_pipeline_id(niche_id: &str) -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("e2e-{}-{:016x}", niche_id, ts)
}

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Public API
// ═══════════════════════════════════════════════════════════════

/// Start a new E2E pipeline by selecting a niche.
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

/// Validate template completeness.
#[pyfunction]
pub fn e2e_validate(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, Py<PyDict>)> {
    let validation = crate::template::template_validate(template_dict, py)?;
    state.set_step(E2EPipelineStep::SafetyCheck);
    Ok((state, validation))
}

/// Run the domain safety + compliance check.
#[pyfunction]
pub fn e2e_safety_check(
    mut state: E2EPipelineState,
    action_type: &str,
    config: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, DomainSafetyCheckResult)> {
    let safety_result = crate::safety_gate_extended::safety_validate_extended(
        action_type,
        config,
        &state.niche_category,
        &state.data_sensitivity,
        py,
    )?;

    if !safety_result.can_proceed {
        state.add_error(format!(
            "Safety check FAILED: final_verdict={}, reason={}",
            safety_result.final_verdict, safety_result.reason,
        ));
        state.set_step(E2EPipelineStep::Error);
    } else {
        state.set_step(E2EPipelineStep::CertifyBlueprint);
    }

    Ok((state, safety_result))
}

/// Certify the blueprint.
#[pyfunction]
pub fn e2e_certify(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, crate::certifier::CertificationResult)> {
    let cert_result = crate::certifier::certifier_from_template(template_dict, py)?;

    if cert_result.success {
        state.set_step(E2EPipelineStep::Export);
    } else {
        state.add_error("Certification failed".to_string());
        for err in cert_result.errors.clone() {
            state.add_error(err);
        }
        state.set_step(E2EPipelineStep::Error);
    }

    Ok((state, cert_result))
}

/// Export the final YAML output.
#[pyfunction]
pub fn e2e_export(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, String)> {
    let yaml_string = crate::template::template_to_yaml(template_dict, py)?;
    state.set_step(E2EPipelineStep::Complete);
    Ok((state, yaml_string))
}

/// Get pipeline progress information.
#[pyfunction]
pub fn e2e_get_progress(state: &E2EPipelineState, py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item("pipeline_id", &state.pipeline_id)?;
    dict.set_item("niche_id", &state.niche_id)?;
    dict.set_item("current_step", &state.current_step)?;
    dict.set_item("progress_pct", state.progress_pct())?;
    dict.set_item("documents_ingested", state.documents_ingested)?;
    dict.set_item("fields_auto_filled", state.fields_auto_filled)?;
    dict.set_item("fields_manual_filled", state.fields_manual_filled)?;
    dict.set_item("total_fields", state.total_fields)?;
    dict.set_item("required_fields", state.required_fields)?;
    dict.set_item("error_count", state.errors.len())?;
    dict.set_item("warning_count", state.warnings.len())?;

    let filled = state.fields_auto_filled + state.fields_manual_filled;
    let completion_pct = if state.total_fields > 0 {
        (filled as f64 / state.total_fields as f64) * 100.0
    } else {
        0.0
    };
    dict.set_item("template_completion_pct", completion_pct)?;

    Ok(dict.unbind())
}
