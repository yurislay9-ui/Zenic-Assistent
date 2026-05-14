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
//!
//! Rust is ideal for this because:
//! - Safety validation is on the critical path for every executor action
//! - Regex matching needs to be fast and deterministic
//! - Rate limiting requires thread-safe concurrent state
//! - The DENY invariant must be enforced at the language level — no monkey-patching

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use regex::Regex;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

// ═══════════════════════════════════════════════════════════════
//  ActionCategory
// ═══════════════════════════════════════════════════════════════

/// Classification of action risk level.
///
/// Mirrors the Python ``ActionCategory`` string-enum exactly:
///
/// ======== ============ ===================================
/// Variant  Python value Meaning
/// ======== ============ ===================================
/// Safe     ``"safe"``   Read-only, non-destructive
/// Moderate ``"moderate"`` Write operations, single record
/// Destructive ``"destructive"`` Delete, drop, bulk operations
/// Financial ``"financial"`` Involves money, invoices, payments
/// System   ``"system"`` System-level changes
/// ======== ============ ===================================
#[pyclass(name = "ActionCategory", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy)]
pub enum ActionCategory {
    Safe,
    Moderate,
    Destructive,
    Financial,
    System,
}

impl ActionCategory {
    /// Return the Python-enum string value (e.g. ``"safe"``).
    fn as_str(&self) -> &'static str {
        match self {
            ActionCategory::Safe => "safe",
            ActionCategory::Moderate => "moderate",
            ActionCategory::Destructive => "destructive",
            ActionCategory::Financial => "financial",
            ActionCategory::System => "system",
        }
    }
}

#[pymethods]
impl ActionCategory {
    /// Python ``str()`` → the enum value string.
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    /// Python ``repr()`` → ``ActionCategory.SAFE`` etc.
    fn __repr__(&self) -> String {
        match self {
            ActionCategory::Safe => "ActionCategory.SAFE".into(),
            ActionCategory::Moderate => "ActionCategory.MODERATE".into(),
            ActionCategory::Destructive => "ActionCategory.DESTRUCTIVE".into(),
            ActionCategory::Financial => "ActionCategory.FINANCIAL".into(),
            ActionCategory::System => "ActionCategory.SYSTEM".into(),
        }
    }
}

// ═══════════════════════════════════════════════════════════════
//  SafetyVerdict
// ═══════════════════════════════════════════════════════════════

/// Safety gate verdict.
///
/// Mirrors the Python ``SafetyVerdict`` string-enum:
///
/// ============ ==================================================
/// Variant      Meaning
/// ============ ==================================================
/// Allow        Action may proceed
/// Confirm      Requires user confirmation before proceeding
/// Approve      Requires higher-role approval
/// Deny         Absolutely denied — **no override**
/// RateLimited  Too many actions, slow down
/// ============ ==================================================
#[pyclass(name = "SafetyVerdict", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy)]
pub enum SafetyVerdict {
    Allow,
    Confirm,
    Approve,
    Deny,
    RateLimited,
}

impl SafetyVerdict {
    fn as_str(&self) -> &'static str {
        match self {
            SafetyVerdict::Allow => "ALLOW",
            SafetyVerdict::Confirm => "CONFIRM",
            SafetyVerdict::Approve => "APPROVE",
            SafetyVerdict::Deny => "DENY",
            SafetyVerdict::RateLimited => "RATE_LIMITED",
        }
    }
}

#[pymethods]
impl SafetyVerdict {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("SafetyVerdict.{}", self.as_str())
    }
}

// ═══════════════════════════════════════════════════════════════
//  SafetyCheckResult
// ═══════════════════════════════════════════════════════════════

/// Result of a safety gate check.
///
/// All fields are **read-only** from Python (private Rust fields
/// exposed via ``#[getter]``).  This guarantees the DENY invariant
/// at the type level — no Python code can mutate a verdict.
///
/// The ``action_id`` is a unique identifier generated per validation.
/// It is the ONLY key that confirm_action/approve_action accept
/// for checking the DENY invariant. This prevents the key-mismatch
/// bypass where denied actions were stored by rule_name but
/// confirm/approve checked by a user-provided action_id.
#[pyclass(name = "SafetyCheckResult")]
#[derive(Clone, Debug)]
pub struct SafetyCheckResult {
    /// Unique action identifier (UUID v4) for this validation result.
    /// Used as the key in DENIED_ACTIONS, CONFIRMATIONS, and APPROVALS.
    action_id: String,
    verdict: SafetyVerdict,
    category: ActionCategory,
    reason: String,
    rule_name: String,
    requires_confirmation: bool,
    requires_approval: bool,
    risk_score: f64,
}

#[pymethods]
impl SafetyCheckResult {
    // ── Read-only getters ──────────────────────────────────────

    #[getter]
    fn action_id(&self) -> &str {
        &self.action_id
    }

    #[getter]
    fn verdict(&self) -> SafetyVerdict {
        self.verdict.clone()
    }

    #[getter]
    fn category(&self) -> ActionCategory {
        self.category.clone()
    }

    #[getter]
    fn reason(&self) -> &str {
        &self.reason
    }

    #[getter]
    fn rule_name(&self) -> &str {
        &self.rule_name
    }

    #[getter]
    fn requires_confirmation(&self) -> bool {
        self.requires_confirmation
    }

    #[getter]
    fn requires_approval(&self) -> bool {
        self.requires_approval
    }

    #[getter]
    fn risk_score(&self) -> f64 {
        self.risk_score
    }

    // ── Convenience helpers ────────────────────────────────────

    /// Return ``True`` if the action can proceed (ALLOW, CONFIRM, or APPROVE).
    ///
    /// Returns ``False`` for DENY and RATE_LIMITED, enforcing the
    /// critical invariant that denied actions must never execute.
    fn can_proceed(&self) -> bool {
        !matches!(
            self.verdict,
            SafetyVerdict::Deny | SafetyVerdict::RateLimited
        )
    }

    fn __repr__(&self) -> String {
        format!(
            "SafetyCheckResult(action_id={}, verdict={}, category={}, reason={:?}, \
             rule_name={:?}, requires_confirmation={}, requires_approval={}, \
             risk_score={})",
            self.action_id,
            self.verdict.as_str(),
            self.category.as_str(),
            self.reason,
            self.rule_name,
            self.requires_confirmation,
            self.requires_approval,
            self.risk_score,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  Internal SafetyRule
// ═══════════════════════════════════════════════════════════════

/// A deterministic safety rule with a pre-compiled regex pattern.
struct SafetyRule {
    name: &'static str,
    category: ActionCategory,
    pattern: Regex,
    verdict: SafetyVerdict,
    message: &'static str,
}

// ═══════════════════════════════════════════════════════════════
//  Compiled Safety Rules (all 10 deterministic rules)
// ═══════════════════════════════════════════════════════════════

static SAFETY_RULES: Lazy<Vec<SafetyRule>> = Lazy::new(|| {
    vec![
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

// ═══════════════════════════════════════════════════════════════
//  Rate-Limiter State (thread-safe)
// ═══════════════════════════════════════════════════════════════

struct RateLimiterState {
    /// Per-action-type timestamps for per-minute limiting.
    timestamps: HashMap<String, Vec<f64>>,
    /// Per-category timestamps for per-hour limiting.
    category_timestamps: HashMap<ActionCategory, Vec<f64>>,
    max_per_minute: usize,
    max_per_hour: usize,
    max_destructive_per_hour: usize,
    max_financial_per_hour: usize,
}

static RATE_LIMITER: Lazy<Mutex<RateLimiterState>> = Lazy::new(|| {
    Mutex::new(RateLimiterState {
        timestamps: HashMap::new(),
        category_timestamps: HashMap::new(),
        max_per_minute: 30,
        max_per_hour: 200,
        max_destructive_per_hour: 10,
        max_financial_per_hour: 20,
    })
});

// ═══════════════════════════════════════════════════════════════
//  Confirmation / Approval / Denied-Action State
// ═══════════════════════════════════════════════════════════════

/// User confirmations: action_id → unix timestamp.
static CONFIRMATIONS: Lazy<Mutex<HashMap<String, f64>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

/// Role-based approvals: action_id → approver_role.
static APPROVALS: Lazy<Mutex<HashMap<String, String>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

/// **DENY-invariant enforcement**: once an action is recorded as denied,
/// ``confirm_action`` and ``approve_action`` will refuse it.
static DENIED_ACTIONS: Lazy<Mutex<HashMap<String, f64>>> =
    Lazy::new(|| Mutex::new(HashMap::new()));

// ═══════════════════════════════════════════════════════════════
//  Internal helpers
// ═══════════════════════════════════════════════════════════════

/// Current time as seconds since the Unix epoch.
fn current_time() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

/// Monotonic counter for generating unique action IDs.
static ACTION_ID_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Generate a unique action ID for each safety validation.
/// Format: "act_{timestamp_ms}_{counter}" — deterministic within a process
/// but unique across calls. This is the ONLY key used in DENIED_ACTIONS,
/// CONFIRMATIONS, and APPROVALS to prevent the key-mismatch bypass.
fn generate_action_id() -> String {
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    let counter = ACTION_ID_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("act_{}_{}", ts_ms, counter)
}

/// Extract a string value from a Python dict, defaulting to empty string.
fn get_config_string(config: &Bound<'_, PyDict>, key: &str) -> String {
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
fn config_to_searchable(action_type: &str, config: &Bound<'_, PyDict>) -> PyResult<String> {
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
fn classify_action_inner(action_type: &str, config: &Bound<'_, PyDict>) -> ActionCategory {
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
        _ => ActionCategory::Moderate,
    }
}

/// Default verdict for a given category when no rule matches.
fn default_verdict(category: &ActionCategory) -> SafetyVerdict {
    match category {
        ActionCategory::Safe => SafetyVerdict::Allow,
        ActionCategory::Moderate => SafetyVerdict::Allow,
        ActionCategory::Destructive => SafetyVerdict::Confirm,
        ActionCategory::Financial => SafetyVerdict::Approve,
        ActionCategory::System => SafetyVerdict::Confirm,
    }
}

/// Risk score for a given category.
fn risk_score(category: &ActionCategory) -> f64 {
    match category {
        ActionCategory::Safe => 0.0,
        ActionCategory::Moderate => 0.3,
        ActionCategory::Destructive => 0.8,
        ActionCategory::Financial => 0.7,
        ActionCategory::System => 0.6,
    }
}

/// Thread-safe rate-limit check **and record**.
///
/// Mirrors the Python ``ActionRateLimiter.check`` method:
/// 1. Prune per-action timestamps older than 60 s and check per-minute limit.
/// 2. Prune per-category timestamps older than 3600 s and check per-hour limit.
/// 3. If not limited, record the current timestamp.
///
/// Returns ``Some(reason_string)`` if rate-limited, ``None`` otherwise.
fn rate_limit_check(action_type: &str, category: &ActionCategory) -> Option<String> {
    let mut state = match RATE_LIMITER.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    };
    let now = current_time();

    // Copy limits to local variables to avoid borrow conflicts
    let max_per_minute = state.max_per_minute;
    let max_per_hour = state.max_per_hour;
    let max_destructive_per_hour = state.max_destructive_per_hour;
    let max_financial_per_hour = state.max_financial_per_hour;

    // ── Per-action per-minute check ────────────────────────────
    let ts = state
        .timestamps
        .entry(action_type.to_string())
        .or_insert_with(Vec::new);
    ts.retain(|t| now - *t < 60.0);
    if ts.len() >= max_per_minute {
        return Some(format!(
            "Rate limited: {} exceeded {}/min",
            action_type, max_per_minute
        ));
    }
    ts.push(now);

    // ── Per-category per-hour check ────────────────────────────
    let cat_ts = state
        .category_timestamps
        .entry(*category)
        .or_insert_with(Vec::new);
    cat_ts.retain(|t| now - *t < 3600.0);

    match category {
        ActionCategory::Destructive => {
            if cat_ts.len() >= max_destructive_per_hour {
                return Some(format!(
                    "Rate limited: destructive actions exceeded {}/hour",
                    max_destructive_per_hour
                ));
            }
        }
        ActionCategory::Financial => {
            if cat_ts.len() >= max_financial_per_hour {
                return Some(format!(
                    "Rate limited: financial actions exceeded {}/hour",
                    max_financial_per_hour
                ));
            }
        }
        _ => {
            if cat_ts.len() >= max_per_hour {
                return Some(format!(
                    "Rate limited: {} actions exceeded {}/hour",
                    category.as_str(),
                    max_per_hour
                ));
            }
        }
    }
    cat_ts.push(now);

    None
}

/// Check all deterministic safety rules against the searchable config.
///
/// Returns the first matching rule's result, or ``None`` if no rule matches.
fn check_rules(
    action_type: &str,
    config: &Bound<'_, PyDict>,
) -> PyResult<Option<SafetyCheckResult>> {
    let searchable = config_to_searchable(action_type, config)?;

    for rule in SAFETY_RULES.iter() {
        if rule.pattern.is_match(&searchable) {
            return Ok(Some(SafetyCheckResult {
                action_id: String::new(), // Will be assigned by safety_validate()
                verdict: rule.verdict.clone(),
                category: rule.category.clone(),
                reason: rule.message.to_string(),
                rule_name: rule.name.to_string(),
                requires_confirmation: rule.verdict == SafetyVerdict::Confirm,
                requires_approval: rule.verdict == SafetyVerdict::Approve,
                risk_score: risk_score(&rule.category),
            }));
        }
    }

    Ok(None)
}

// ═══════════════════════════════════════════════════════════════
//  PyO3-exposed functions
// ═══════════════════════════════════════════════════════════════

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
///
/// Parameters
/// ----------
/// action_type : str
///     The type of action being performed.
/// config : dict
///     Configuration dict with action-specific parameters.
///
/// Returns
/// -------
/// SafetyCheckResult
///     The safety check result with verdict, category, reason, etc.
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
                denied.insert(result.action_id.clone(), current_time());
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
///
/// Parameters
/// ----------
/// action_type : str
///     The type of action to check.
/// category : ActionCategory
///     The risk category of the action.
///
/// Returns
/// -------
/// str or None
///     Reason string if rate-limited, ``None`` otherwise.
#[pyfunction]
#[pyo3(signature = (action_type, category))]
pub fn check_rate_limit(action_type: &str, category: &ActionCategory) -> Option<String> {
    rate_limit_check(action_type, category)
}

/// Record user confirmation for an action that required it.
///
/// **INVARIANT**: Cannot confirm a DENY'd action.  Always returns
/// ``False`` for actions that received a ``DENY`` verdict.
///
/// Parameters
/// ----------
/// action_id : str
///     The ID of the action to confirm.
///
/// Returns
/// -------
/// bool
///     ``True`` if confirmation was recorded, ``False`` if the
///     action was denied.
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
///
/// Parameters
/// ----------
/// action_id : str
///     The ID of the action to approve.
/// approver_role : str
///     The role of the approver (e.g. ``"admin"``, ``"finance_manager"``).
///
/// Returns
/// -------
/// bool
///     ``True`` if approval was recorded, ``False`` if the
///     action was denied.
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
///
/// Parameters
/// ----------
/// action_id : str
///     The ID of the action to check.
///
/// Returns
/// -------
/// bool
///     ``True`` if the action has been confirmed.
#[pyfunction]
#[pyo3(signature = (action_id))]
pub fn is_confirmed(action_id: &str) -> bool {
    match CONFIRMATIONS.lock() {
        Ok(guard) => guard.contains_key(action_id),
        Err(poisoned) => poisoned.into_inner().contains_key(action_id),
    }
}

/// Check if an action has been approved.
///
/// Parameters
/// ----------
/// action_id : str
///     The ID of the action to check.
///
/// Returns
/// -------
/// bool
///     ``True`` if the action has been approved.
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
fn reset_safety_gate() {
    if let Ok(mut limiter) = RATE_LIMITER.lock() {
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
        assert_eq!(SAFETY_RULES.len(), 10);
    }

    #[test]
    fn test_rule_drop_table_is_deny() {
        assert_eq!(SAFETY_RULES[1].name, "drop_table");
        assert_eq!(SAFETY_RULES[1].verdict, SafetyVerdict::Deny);
        assert!(SAFETY_RULES[1].pattern.is_match("DROP TABLE users"));
        assert!(SAFETY_RULES[1].pattern.is_match("drop table users"));
    }

    #[test]
    fn test_rule_truncate_is_deny() {
        assert_eq!(SAFETY_RULES[2].name, "truncate_table");
        assert_eq!(SAFETY_RULES[2].verdict, SafetyVerdict::Deny);
        assert!(SAFETY_RULES[2].pattern.is_match("TRUNCATE TABLE users"));
    }

    #[test]
    fn test_rule_mass_delete_is_confirm() {
        assert_eq!(SAFETY_RULES[0].name, "mass_delete");
        assert_eq!(SAFETY_RULES[0].verdict, SafetyVerdict::Confirm);
        assert!(SAFETY_RULES[0].pattern.is_match("DELETE FROM users WHERE id > 100;"));
    }

    #[test]
    fn test_rule_invoice_is_approve() {
        assert_eq!(SAFETY_RULES[4].name, "invoice_create");
        assert_eq!(SAFETY_RULES[4].verdict, SafetyVerdict::Approve);
        assert!(SAFETY_RULES[4].pattern.is_match("generate invoice for client"));
    }

    #[test]
    fn test_default_verdict_mapping() {
        assert_eq!(default_verdict(&ActionCategory::Safe), SafetyVerdict::Allow);
        assert_eq!(
            default_verdict(&ActionCategory::Moderate),
            SafetyVerdict::Allow
        );
        assert_eq!(
            default_verdict(&ActionCategory::Destructive),
            SafetyVerdict::Confirm
        );
        assert_eq!(
            default_verdict(&ActionCategory::Financial),
            SafetyVerdict::Approve
        );
        assert_eq!(
            default_verdict(&ActionCategory::System),
            SafetyVerdict::Confirm
        );
    }

    #[test]
    fn test_risk_score_mapping() {
        assert_eq!(risk_score(&ActionCategory::Safe), 0.0);
        assert_eq!(risk_score(&ActionCategory::Moderate), 0.3);
        assert_eq!(risk_score(&ActionCategory::Destructive), 0.8);
        assert_eq!(risk_score(&ActionCategory::Financial), 0.7);
        assert_eq!(risk_score(&ActionCategory::System), 0.6);
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
            if let Ok(mut denied) = DENIED_ACTIONS.lock() {
                denied.insert(deny_action_id.to_string(), current_time());
            }
        }
        // confirm_action and approve_action MUST refuse this action_id
        assert!(!confirm_action(deny_action_id));
        assert!(!approve_action(deny_action_id, "admin"));

        // But a DIFFERENT action_id should still work
        assert!(confirm_action("act_other_456"));
        assert!(approve_action("act_other_789", "admin"));

        // Clean up
        reset_safety_gate();
    }

    #[test]
    fn test_confirm_and_approve_flow() {
        reset_safety_gate();

        assert!(confirm_action("confirm_test_action"));
        assert!(is_confirmed("confirm_test_action"));
        assert!(!is_approved("confirm_test_action"));

        assert!(approve_action("approve_test_action", "finance_manager"));
        assert!(is_approved("approve_test_action"));
        assert!(!is_confirmed("approve_test_action"));

        reset_safety_gate();
        assert!(!is_confirmed("confirm_test_action"));
        assert!(!is_approved("approve_test_action"));
    }
}
