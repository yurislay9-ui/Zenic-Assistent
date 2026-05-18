// ─── Safety Gate Validation ──────────────────────────────────────────────
// safety_validate(), check_rate_limit()

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::classify::classify_action_inner;
use super::rate_limiter::rate_limit_check;
use super::rules::check_rules;
use super::state::{generate_action_id, DENIED_ACTIONS};
use super::types::*;

/// Run all safety checks for an action.
///
/// This is the core validation function that:
/// 1. Classifies the action into a risk category
/// 2. Checks all 10 deterministic safety rules (regex matching)
/// 3. Applies per-action and per-category rate limiting
/// 4. Returns the verdict with full details
///
/// **INVARIANT**: If the verdict is ``DENY``, no override exists.
/// This is enforced at the Rust level — ``SafetyCheckResult`` is
/// immutable and there is no override mechanism.
#[pyfunction]
#[pyo3(signature = (action_type, config))]
pub fn safety_validate(
    action_type: &str,
    config: &Bound<'_, PyDict>,
) -> PyResult<SafetyCheckResult> {
    // Generate a unique action_id for this validation.
    // This is the ONLY key used in DENIED_ACTIONS, CONFIRMATIONS, APPROVALS.
    let action_id = generate_action_id();

    // Step 1 — classify the action
    let category = classify_action_inner(action_type, config);

    // Step 2 — check deterministic safety rules
    if let Some(mut result) = check_rules(action_type, config)? {
        // Assign the unique action_id to this result.
        result.action_id = action_id;

        // ── DENY invariant ─────────────────────────────────────
        // Record the denied action by action_id (NOT rule_name!)
        // so confirm/approve can check the SAME key.
        if result.verdict == SafetyVerdict::Deny {
            if let Ok(mut denied) = DENIED_ACTIONS.lock() {
                denied.insert(result.action_id.clone(), super::rate_limiter::current_time());
            }
        }
        return Ok(result);
    }

    // Step 3 — check rate limits
    if let Some(rate_reason) = rate_limit_check(action_type, &category) {
        return Ok(SafetyCheckResult {
            action_id,
            verdict: SafetyVerdict::RateLimited,
            category,
            reason: rate_reason,
            rule_name: "rate_limiter".to_string(),
            requires_confirmation: false,
            requires_approval: false,
            risk_score: 0.6,
        });
    }

    // Step 4 — default verdict based on category
    let verdict = default_verdict(&category);

    let category_str = category.as_str().to_string();
    let risk = risk_score(&category);
    let req_confirm = verdict == SafetyVerdict::Confirm;
    let req_approve = verdict == SafetyVerdict::Approve;

    Ok(SafetyCheckResult {
        action_id,
        verdict,
        category,
        reason: format!("Action classified as {}", category_str),
        rule_name: "default_category_verdict".to_string(),
        requires_confirmation: req_confirm,
        requires_approval: req_approve,
        risk_score: risk,
    })
}

/// Check if an action is rate-limited.
///
/// Also **records** the current timestamp if the action is *not*
/// rate-limited (same semantics as the Python ``ActionRateLimiter.check``).
#[pyfunction]
#[pyo3(signature = (action_type, category))]
pub fn check_rate_limit(action_type: &str, category: &ActionCategory) -> Option<String> {
    rate_limit_check(action_type, category)
}
