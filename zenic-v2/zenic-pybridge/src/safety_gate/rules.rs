// ─── Safety Gate Rules ───────────────────────────────────────────────────
// SAFETY_RULES static, check_rules()

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use regex::Regex;

use super::types::*;

// ═══════════════════════════════════════════════════════════════
//  Compiled Safety Rules (all 14 deterministic rules)
//
//  FIX A1: Added 4 missing DENY rules that Python had but Rust
//  was missing: shell_destructive, shell_injection,
//  data_exfiltration, sensitive_file_access.
//
//  These MUST appear first so they take precedence. Combined with
//  the A3 fix (severity escalation), the ordering within each
//  severity group no longer matters for correctness, but we keep
//  the same order as Python for maintainability.
// ═══════════════════════════════════════════════════════════════

pub(crate) static SAFETY_RULES: Lazy<Vec<SafetyRule>> = Lazy::new(|| {
    vec![
        // ── DESTRUCTIVE: Shell commands & injection (CRITICAL — checked first) ──
        SafetyRule {
            name: "shell_destructive",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\b(?:rm\s+-rf|sudo\s+|chmod\s+|chown\s+|format\s+[A-Z]:|mkfs\.)\b")
                .expect("invalid regex: shell_destructive"),
            verdict: SafetyVerdict::Deny,
            message: "Destructive shell command detected — DENIED",
        },
        SafetyRule {
            name: "shell_injection",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\b(?:eval\s*\(|exec\s*\(|subprocess|os\.system|os\.popen|__import__)\b")
                .expect("invalid regex: shell_injection"),
            verdict: SafetyVerdict::Deny,
            message: "Code injection pattern detected — DENIED",
        },
        SafetyRule {
            name: "data_exfiltration",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\b(?:curl\s+.*(?:password|secret|token|api_key)|wget\s+.*(?:password|secret|token)|\.post\s*\(\s*[\"']https?://.*(?:password|token|key))\b")
                .expect("invalid regex: data_exfiltration"),
            verdict: SafetyVerdict::Deny,
            message: "Potential data exfiltration detected — DENIED",
        },
        SafetyRule {
            name: "sensitive_file_access",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\b(?:/etc/shadow|/etc/passwd|\.ssh/|\.env|\.aws/|id_rsa)\b")
                .expect("invalid regex: sensitive_file_access"),
            verdict: SafetyVerdict::Deny,
            message: "Sensitive file access detected — DENIED",
        },
        // ── DESTRUCTIVE: Mass deletions ─────────────────────────
        SafetyRule {
            name: "mass_delete",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\bDELETE\s+FROM\s+\w+\s*(?:WHERE\s+.+)?\s*;?\s*$")
                .expect("invalid regex: mass_delete"),
            verdict: SafetyVerdict::Confirm,
            message: "Mass DELETE detected — requires explicit confirmation",
        },
        SafetyRule {
            name: "drop_table",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\bDROP\s+(TABLE|INDEX|VIEW|TRIGGER|DATABASE)\b")
                .expect("invalid regex: drop_table"),
            verdict: SafetyVerdict::Deny,
            message: "DROP statement detected — absolutely denied for safety",
        },
        SafetyRule {
            name: "truncate_table",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\bTRUNCATE\s+(TABLE\s+)?\w+")
                .expect("invalid regex: truncate_table"),
            verdict: SafetyVerdict::Deny,
            message: "TRUNCATE detected — denied, use DELETE with WHERE clause",
        },
        SafetyRule {
            name: "bulk_update",
            category: ActionCategory::Destructive,
            pattern: Regex::new(r"(?i)\bUPDATE\s+\w+\s+SET\s+.+(?:\s+WHERE\s+.+)?$")
                .expect("invalid regex: bulk_update"),
            verdict: SafetyVerdict::Confirm,
            message: "UPDATE without WHERE or bulk UPDATE — requires confirmation",
        },
        // ── FINANCIAL: Money-related operations ─────────────────
        SafetyRule {
            name: "invoice_create",
            category: ActionCategory::Financial,
            pattern: Regex::new(r"(?i)(?:invoice|factura|receipt|pago|payment)")
                .expect("invalid regex: invoice_create"),
            verdict: SafetyVerdict::Approve,
            message: "Financial document creation — requires approval",
        },
        SafetyRule {
            name: "payment_process",
            category: ActionCategory::Financial,
            pattern: Regex::new(r"(?i)(?:charge|cobro|refund|reembolso|transfer|transferencia)")
                .expect("invalid regex: payment_process"),
            verdict: SafetyVerdict::Approve,
            message: "Payment processing — requires approval from financial role",
        },
        SafetyRule {
            name: "price_change",
            category: ActionCategory::Financial,
            pattern: Regex::new(
                r"(?i)(?:price|precio|discount|descuento|rate|tarifa).*(?:change|update|modify)",
            )
            .expect("invalid regex: price_change"),
            verdict: SafetyVerdict::Approve,
            message: "Price modification — requires approval",
        },
        // ── SYSTEM: System-level operations ─────────────────────
        SafetyRule {
            name: "db_backup",
            category: ActionCategory::System,
            pattern: Regex::new(r"(?i)\bbackup\b").expect("invalid regex: db_backup"),
            verdict: SafetyVerdict::Confirm,
            message: "Database backup operation — requires confirmation",
        },
        SafetyRule {
            name: "schema_migration",
            category: ActionCategory::System,
            pattern: Regex::new(
                r"(?i)(?:ALTER\s+TABLE|CREATE\s+TABLE|ADD\s+COLUMN|DROP\s+COLUMN)",
            )
            .expect("invalid regex: schema_migration"),
            verdict: SafetyVerdict::Approve,
            message: "Schema migration — requires admin approval",
        },
        SafetyRule {
            name: "cron_schedule",
            category: ActionCategory::System,
            pattern: Regex::new(r"(?i)(?:cron|schedule|interval)")
                .expect("invalid regex: cron_schedule"),
            verdict: SafetyVerdict::Confirm,
            message: "Scheduling operation — requires confirmation to avoid spam",
        },
    ]
});

/// Severity ordering for verdict escalation.
///
/// FIX A3: Mirrors the Python `_SEVERITY_ORDER` exactly.
/// When multiple rules match, the most severe verdict wins.
const fn severity_order(v: &SafetyVerdict) -> u8 {
    match v {
        SafetyVerdict::Allow => 0,
        SafetyVerdict::Confirm => 1,
        SafetyVerdict::Approve => 2,
        SafetyVerdict::RateLimited => 3,
        SafetyVerdict::Deny => 4,
    }
}

/// Check all deterministic safety rules against the searchable config.
///
/// FIX A3: Iterates ALL rules and returns the MOST SEVERE match,
/// mirroring the Python `_check_rules()` escalation logic exactly.
/// Previously returned the FIRST match, which allowed a CONFIRM rule
/// appearing before a DENY rule to bypass the DENY.
pub(crate) fn check_rules(
    action_type: &str,
    config: &Bound<'_, PyDict>,
) -> PyResult<Option<SafetyCheckResult>> {
    let searchable = super::classify::config_to_searchable(action_type, config)?;

    let mut worst_result: Option<SafetyCheckResult> = None;
    let mut worst_severity: u8 = 0;

    for rule in SAFETY_RULES.iter() {
        if rule.pattern.is_match(&searchable) {
            let rule_severity = severity_order(&rule.verdict);
            // Escalate: keep the result associated with the most severe verdict
            if rule_severity >= worst_severity {
                worst_severity = rule_severity;
                worst_result = Some(SafetyCheckResult {
                    action_id: String::new(), // Will be assigned by safety_validate()
                    verdict: rule.verdict.clone(),
                    category: rule.category.clone(),
                    reason: rule.message.to_string(),
                    rule_name: rule.name.to_string(),
                    requires_confirmation: rule.verdict == SafetyVerdict::Confirm,
                    requires_approval: rule.verdict == SafetyVerdict::Approve,
                    risk_score: risk_score(&rule.category),
                });
            }
        }
    }

    Ok(worst_result)
}
