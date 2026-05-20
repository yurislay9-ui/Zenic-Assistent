//! Safety Gate — Deterministic safety validation engine for Zenic-Agents.
//!
//! This module implements the Safety Gate core in Rust for:
//! - Deterministic action classification (SAFE, MODERATE, DESTRUCTIVE, FINANCIAL, SYSTEM)
//! - 10 compiled-regex safety rules evaluated on every executor action
//! - Thread-safe per-action and per-category rate limiting
//! - Confirmation and approval tracking
//!
//! # CRITICAL INVARIANT
//!
//! If the verdict is **DENY**, no override exists. This is enforced at the
//! Rust level:
//! - `SafetyCheckResult` fields are private with read-only `#[getter]` access
//! - No `set_verdict`, `override_verdict`, or mutation method exists
//! - `confirm_action` and `approve_action` refuse denied actions
//! - The Rust type system makes it **impossible** to mutate a verdict

pub mod types;
pub mod rules;
pub mod rate_limiter;
pub mod state;
pub mod classify;
pub mod validate;

pub use types::{ActionCategory, SafetyVerdict, SafetyCheckResult};
pub use classify::classify_action;
pub use validate::{safety_validate, check_rate_limit};
pub use state::{confirm_action, approve_action, is_confirmed, is_approved};

// ═══════════════════════════════════════════════════════════════
//  Unit tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_action_category_str_roundtrip() {
        assert_eq!(ActionCategory::Safe.as_str(), "safe");
        assert_eq!(ActionCategory::Moderate.as_str(), "moderate");
        assert_eq!(ActionCategory::Destructive.as_str(), "destructive");
        assert_eq!(ActionCategory::Financial.as_str(), "financial");
        assert_eq!(ActionCategory::System.as_str(), "system");
    }

    #[test]
    fn test_safety_verdict_str_roundtrip() {
        assert_eq!(SafetyVerdict::Allow.as_str(), "ALLOW");
        assert_eq!(SafetyVerdict::Confirm.as_str(), "CONFIRM");
        assert_eq!(SafetyVerdict::Approve.as_str(), "APPROVE");
        assert_eq!(SafetyVerdict::Deny.as_str(), "DENY");
        assert_eq!(SafetyVerdict::RateLimited.as_str(), "RATE_LIMITED");
    }

    #[test]
    fn test_all_ten_rules_compiled() {
        assert_eq!(rules::SAFETY_RULES.len(), 10);
    }

    #[test]
    fn test_rule_drop_table_is_deny() {
        assert_eq!(rules::SAFETY_RULES[1].name, "drop_table");
        assert_eq!(rules::SAFETY_RULES[1].verdict, SafetyVerdict::Deny);
        assert!(rules::SAFETY_RULES[1].pattern.is_match("DROP TABLE users"));
        assert!(rules::SAFETY_RULES[1].pattern.is_match("drop table users"));
    }

    #[test]
    fn test_rule_truncate_is_deny() {
        assert_eq!(rules::SAFETY_RULES[2].name, "truncate_table");
        assert_eq!(rules::SAFETY_RULES[2].verdict, SafetyVerdict::Deny);
        assert!(rules::SAFETY_RULES[2].pattern.is_match("TRUNCATE TABLE users"));
    }

    #[test]
    fn test_rule_mass_delete_is_confirm() {
        assert_eq!(rules::SAFETY_RULES[0].name, "mass_delete");
        assert_eq!(rules::SAFETY_RULES[0].verdict, SafetyVerdict::Confirm);
        assert!(rules::SAFETY_RULES[0].pattern.is_match("DELETE FROM users WHERE id > 100;"));
    }

    #[test]
    fn test_rule_invoice_is_approve() {
        assert_eq!(rules::SAFETY_RULES[4].name, "invoice_create");
        assert_eq!(rules::SAFETY_RULES[4].verdict, SafetyVerdict::Approve);
        assert!(rules::SAFETY_RULES[4].pattern.is_match("generate invoice for client"));
    }

    #[test]
    fn test_default_verdict_mapping() {
        assert_eq!(types::default_verdict(&ActionCategory::Safe), SafetyVerdict::Allow);
        assert_eq!(
            types::default_verdict(&ActionCategory::Moderate),
            SafetyVerdict::Allow
        );
        assert_eq!(
            types::default_verdict(&ActionCategory::Destructive),
            SafetyVerdict::Confirm
        );
        assert_eq!(
            types::default_verdict(&ActionCategory::Financial),
            SafetyVerdict::Approve
        );
        assert_eq!(
            types::default_verdict(&ActionCategory::System),
            SafetyVerdict::Confirm
        );
    }

    #[test]
    fn test_risk_score_mapping() {
        assert_eq!(types::risk_score(&ActionCategory::Safe), 0.0);
        assert_eq!(types::risk_score(&ActionCategory::Moderate), 0.3);
        assert_eq!(types::risk_score(&ActionCategory::Destructive), 0.8);
        assert_eq!(types::risk_score(&ActionCategory::Financial), 0.7);
        assert_eq!(types::risk_score(&ActionCategory::System), 0.6);
    }

    #[test]
    fn test_can_proceed_deny_is_false() {
        let result = SafetyCheckResult {
            action_id: "act_test_1".to_string(),
            verdict: SafetyVerdict::Deny,
            category: ActionCategory::Destructive,
            reason: "test".into(),
            rule_name: "test".into(),
            requires_confirmation: false,
            requires_approval: false,
            risk_score: 0.8,
        };
        assert!(!result.can_proceed());
    }

    #[test]
    fn test_can_proceed_allow_is_true() {
        let result = SafetyCheckResult {
            action_id: "act_test_2".to_string(),
            verdict: SafetyVerdict::Allow,
            category: ActionCategory::Safe,
            reason: "test".into(),
            rule_name: "test".into(),
            requires_confirmation: false,
            requires_approval: false,
            risk_score: 0.0,
        };
        assert!(result.can_proceed());
    }

    #[test]
    fn test_deny_invariant_confirm_refused() {
        // Record an action as denied using action_id (NOT rule_name)
        let deny_action_id = "act_deny_test_123";
        {
            if let Ok(mut denied) = state::DENIED_ACTIONS.lock() {
                denied.insert(deny_action_id.to_string(), rate_limiter::current_time());
            }
        }
        // confirm_action and approve_action MUST refuse this action_id
        assert!(!confirm_action(deny_action_id));
        assert!(!approve_action(deny_action_id, "admin"));

        // But a DIFFERENT action_id should still work
        assert!(confirm_action("act_other_456"));
        assert!(approve_action("act_other_789", "admin"));

        // Clean up
        state::reset_safety_gate();
    }

    #[test]
    fn test_confirm_and_approve_flow() {
        state::reset_safety_gate();

        assert!(confirm_action("confirm_test_action"));
        assert!(is_confirmed("confirm_test_action"));
        assert!(!is_approved("confirm_test_action"));

        assert!(approve_action("approve_test_action", "finance_manager"));
        assert!(is_approved("approve_test_action"));
        assert!(!is_confirmed("approve_test_action"));

        state::reset_safety_gate();
        assert!(!is_confirmed("confirm_test_action"));
        assert!(!is_approved("approve_test_action"));
    }
}
