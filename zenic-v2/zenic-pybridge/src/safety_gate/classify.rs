// ─── Safety Gate Action Classification ───────────────────────────────────
// classify_action_inner(), config_to_searchable(), get_config_string(), classify_action() (pub)
//
// IMPORTANT: This classification logic must stay synchronized with
// zenic-safety/src/engine/gate.rs classify_action(). Any changes here
// MUST be mirrored there, and vice versa.
// See: H-84 architectural finding — classification divergence.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use super::types::ActionCategory;

/// Extract a string value from a Python dict, defaulting to empty string.
pub(crate) fn get_config_string(config: &Bound<'_, PyDict>, key: &str) -> String {
    config
        .get_item(key)
        .ok()
        .flatten()
        .and_then(|v| v.extract::<String>().ok())
        .unwrap_or_default()
}

/// Convert a Python config dict into a single searchable string for
/// regex rule matching, mirroring the Python ``_config_to_searchable``
/// method exactly.
pub(crate) fn config_to_searchable(action_type: &str, config: &Bound<'_, PyDict>) -> PyResult<String> {
    let mut parts: Vec<String> = vec![action_type.to_string()];

    for (_, value) in config.iter() {
        // Try plain string first (avoids repr quotes in output)
        if let Ok(s) = value.extract::<String>() {
            parts.push(s);
        } else if let Ok(list) = value.downcast::<PyList>() {
            // Extend with stringified elements of a Python list
            for item in list.iter() {
                parts.push(item.str()?.extract::<String>()?);
            }
        } else if let Ok(tuple) = value.downcast::<PyTuple>() {
            // Extend with stringified elements of a Python tuple
            for item in tuple.iter() {
                parts.push(item.str()?.extract::<String>()?);
            }
        } else {
            // Fallback: ``str(value)`` for ints, floats, etc.
            parts.push(value.str()?.extract::<String>()?);
        }
    }

    Ok(parts.join(" "))
}

/// Deterministic action → category classification.
///
/// Replicates the Python ``SafetyGate._classify_action`` logic exactly.
pub(crate) fn classify_action_inner(action_type: &str, config: &Bound<'_, PyDict>) -> ActionCategory {
    let action_lower = action_type.to_lowercase();

    match action_lower.as_str() {
        "database" | "db" | "database_operation" => {
            let operation = get_config_string(config, "operation").to_lowercase();
            let query = get_config_string(config, "query").to_uppercase();

            if query.contains("DELETE") || operation == "delete" {
                return ActionCategory::Destructive;
            }
            if query.contains("DROP") || query.contains("TRUNCATE") {
                return ActionCategory::Destructive;
            }
            if query.contains("INSERT") || query.contains("UPDATE") {
                return ActionCategory::Moderate;
            }
            if operation.contains("backup") || operation.contains("script") {
                return ActionCategory::System;
            }
            ActionCategory::Safe
        }
        "email" | "send_email" => {
            let subject = get_config_string(config, "subject").to_lowercase();
            let body = get_config_string(config, "body").to_lowercase();
            let combined = format!("{} {}", subject, body);
            let financial_keywords = ["invoice", "factura", "payment", "pago", "refund"];
            if financial_keywords.iter().any(|kw| combined.contains(kw)) {
                return ActionCategory::Financial;
            }
            ActionCategory::Moderate
        }
        "file" | "file_operation" => {
            let operation = get_config_string(config, "operation").to_lowercase();
            match operation.as_str() {
                "delete" | "move" => ActionCategory::Destructive,
                "write" | "append" => ActionCategory::Moderate,
                _ => ActionCategory::Safe,
            }
        }
        "schedule" => ActionCategory::System,
        "notification" | "send_notification" => ActionCategory::Safe,
        "http" | "http_request" | "webhook" => {
            let method_raw = get_config_string(config, "method");
            let method = if method_raw.is_empty() {
                "GET".to_string()
            } else {
                method_raw.to_uppercase()
            };
            match method.as_str() {
                "DELETE" | "PUT" => ActionCategory::Moderate,
                _ => ActionCategory::Safe,
            }
        }
        "transform" | "data_transform" => ActionCategory::Safe,
        "discord" => ActionCategory::Moderate,
        "niche_onboarding" => ActionCategory::Moderate,
        _ => ActionCategory::Moderate,
    }
}

/// Classify an action into a risk category (deterministic).
///
/// Parameters
/// ----------
/// action_type : str
///     The type of action being performed (e.g. ``"database"``, ``"email"``).
/// config : dict
///     Configuration dict with action-specific parameters.
///
/// Returns
/// -------
/// ActionCategory
///     The risk category classification.
#[pyfunction]
#[pyo3(signature = (action_type, config))]
pub fn classify_action(action_type: &str, config: &Bound<'_, PyDict>) -> ActionCategory {
    classify_action_inner(action_type, config)
}
