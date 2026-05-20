// ─── Safety Gate Rate Limiter ────────────────────────────────────────────
// RateLimiterState, RATE_LIMITER static, rate_limit_check(), current_time()

use once_cell::sync::Lazy;
use std::collections::HashMap;
use std::sync::Mutex;

use super::types::ActionCategory;

// ═══════════════════════════════════════════════════════════════
//  Rate-Limiter State (thread-safe)
// ═══════════════════════════════════════════════════════════════

pub(crate) struct RateLimiterState {
    /// Per-action-type timestamps for per-minute limiting.
    pub timestamps: HashMap<String, Vec<f64>>,
    /// Per-category timestamps for per-hour limiting.
    pub category_timestamps: HashMap<ActionCategory, Vec<f64>>,
    pub max_per_minute: usize,
    pub max_per_hour: usize,
    pub max_destructive_per_hour: usize,
    pub max_financial_per_hour: usize,
}

pub(crate) static RATE_LIMITER: Lazy<Mutex<RateLimiterState>> = Lazy::new(|| {
    Mutex::new(RateLimiterState {
        timestamps: HashMap::new(),
        category_timestamps: HashMap::new(),
        max_per_minute: 30,
        max_per_hour: 200,
        max_destructive_per_hour: 10,
        max_financial_per_hour: 20,
    })
});

/// Current time as seconds since the Unix epoch.
pub(crate) fn current_time() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

/// Thread-safe rate-limit check **and record**.
///
/// Mirrors the Python ``ActionRateLimiter.check`` method:
/// 1. Prune per-action timestamps older than 60 s and check per-minute limit.
/// 2. Prune per-category timestamps older than 3600 s and check per-hour limit.
/// 3. If not limited, record the current timestamp.
///
/// Returns ``Some(reason_string)`` if rate-limited, ``None`` otherwise.
pub(crate) fn rate_limit_check(action_type: &str, category: &ActionCategory) -> Option<String> {
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
