// ─── Safety Gate State (Confirmations / Approvals / Denied) ──────────────
// CONFIRMATIONS, APPROVALS, DENIED_ACTIONS statics, ACTION_ID_COUNTER,
// generate_action_id(), confirm_action(), approve_action(), is_confirmed(), is_approved()

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use super::rate_limiter::current_time;

/// User confirmations: action_id → unix timestamp.
pub(crate) static CONFIRMATIONS: Lazy<Mutex<HashMap<String, f64>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

/// Role-based approvals: action_id → approver_role.
pub(crate) static APPROVALS: Lazy<Mutex<HashMap<String, String>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

/// **DENY-invariant enforcement**: once an action is recorded as denied,
/// ``confirm_action`` and ``approve_action`` will refuse it.
pub(crate) static DENIED_ACTIONS: Lazy<Mutex<HashMap<String, f64>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

/// Monotonic counter for generating unique action IDs.
static ACTION_ID_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Generate a unique action ID for each safety validation.
/// Format: "act_{timestamp_ms}_{counter}" — deterministic within a process
/// but unique across calls. This is the ONLY key used in DENIED_ACTIONS,
/// CONFIRMATIONS, and APPROVALS to prevent the key-mismatch bypass.
pub(crate) fn generate_action_id() -> String {
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let counter = ACTION_ID_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("act_{}_{}", ts_ms, counter)
}

/// Record user confirmation for an action that required it.
///
/// **INVARIANT**: Cannot confirm a DENY'd action.  Always returns
/// ``False`` for actions that received a ``DENY`` verdict.
#[pyfunction]
#[pyo3(signature = (action_id))]
pub fn confirm_action(action_id: &str) -> bool {
    // ── DENY invariant enforcement ─────────────────────────────
    if let Ok(denied) = DENIED_ACTIONS.lock() {
        if denied.contains_key(action_id) {
            return false;
        }
    }

    if let Ok(mut confirmations) = CONFIRMATIONS.lock() {
        confirmations.insert(action_id.to_string(), current_time());
    }
    true
}

/// Record role-based approval for an action that required it.
///
/// **INVARIANT**: Cannot approve a DENY'd action.  Always returns
/// ``False`` for actions that received a ``DENY`` verdict.
#[pyfunction]
#[pyo3(signature = (action_id, approver_role))]
pub fn approve_action(action_id: &str, approver_role: &str) -> bool {
    // ── DENY invariant enforcement ─────────────────────────────
    if let Ok(denied) = DENIED_ACTIONS.lock() {
        if denied.contains_key(action_id) {
            return false;
        }
    }

    if let Ok(mut approvals) = APPROVALS.lock() {
        approvals.insert(action_id.to_string(), approver_role.to_string());
    }
    true
}

/// Check if an action has been confirmed.
#[pyfunction]
#[pyo3(signature = (action_id))]
pub fn is_confirmed(action_id: &str) -> bool {
    match CONFIRMATIONS.lock() {
        Ok(guard) => guard.contains_key(action_id),
        Err(poisoned) => poisoned.into_inner().contains_key(action_id),
    }
}

/// Check if an action has been approved.
#[pyfunction]
#[pyo3(signature = (action_id))]
pub fn is_approved(action_id: &str) -> bool {
    match APPROVALS.lock() {
        Ok(guard) => guard.contains_key(action_id),
        Err(poisoned) => poisoned.into_inner().contains_key(action_id),
    }
}

/// Reset the safety gate state (for testing ONLY).
///
/// ⚠️ SECURITY: This function is NOT exposed to Python via PyO3.
/// It exists solely for Rust unit tests. Clearing DENIED_ACTIONS
/// from Python would violate the DENY invariant.
#[cfg(test)]
pub(crate) fn reset_safety_gate() {
    if let Ok(mut limiter) = super::rate_limiter::RATE_LIMITER.lock() {
        limiter.timestamps.clear();
        limiter.category_timestamps.clear();
    }
    if let Ok(mut confirmations) = CONFIRMATIONS.lock() {
        confirmations.clear();
    }
    if let Ok(mut approvals) = APPROVALS.lock() {
        approvals.clear();
    }
    if let Ok(mut denied) = DENIED_ACTIONS.lock() {
        denied.clear();
    }
}
