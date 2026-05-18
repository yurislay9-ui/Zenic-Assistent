//! PyO3 API — Answer submission and progress functions.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use super::result_types::*;
use super::types::*;
use super::validation::*;

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
