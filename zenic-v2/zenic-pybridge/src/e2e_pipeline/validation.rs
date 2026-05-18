//! E2E Pipeline late stages: validate, safety check, certify, export, progress.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::safety_gate_extended::DomainSafetyCheckResult;

use super::types::{E2EPipelineStep, E2EPipelineState};

/// Validate template completeness.
///
/// This is step 5 of the pipeline. It checks if all required
/// fields have been filled.
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
/// dict
///     Validation result with keys: valid, total_fields, filled_fields,
///     missing_required, completion_pct, status.
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
///
/// This is step 6 of the pipeline. It runs the extended safety
/// gate including domain-specific rules and compliance validation.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// action_type : str
///     The action type (e.g., "niche_onboarding").
/// config : dict
///     Configuration dict for the safety check.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, DomainSafetyCheckResult]
///     (updated_state, safety_result).
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
///
/// This is step 7 of the pipeline. It converts the completed
/// template into a CertifiedBlueprint with ECDSA signature.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// template_dict : dict
///     The completed template dict.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, CertificationResult]
///     (updated_state, certification_result).
#[pyfunction]
pub fn e2e_certify(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, crate::certifier::CertificationResult)> {
    let cert_result = crate::certifier::certifier_from_template(template_dict, py)?;

    if cert_result.success() {
        state.set_step(E2EPipelineStep::Export);
    } else {
        state.add_error("Certification failed".to_string());
        for err in cert_result.errors() {
            state.add_error(err);
        }
        state.set_step(E2EPipelineStep::Error);
    }

    Ok((state, cert_result))
}

/// Export the final YAML output.
///
/// This is step 8 of the pipeline. It serializes the completed
/// template to YAML format.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// template_dict : dict
///     The completed template dict.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, str]
///     (updated_state, yaml_string).
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
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
///
/// Returns
/// -------
/// dict
///     Progress info with step, percentage, and field counts.
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
