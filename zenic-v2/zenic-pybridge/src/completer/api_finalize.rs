//! PyO3 API — Finalization and suggestions functions.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::result_types::*;
use super::types::*;
use super::validation::*;

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
