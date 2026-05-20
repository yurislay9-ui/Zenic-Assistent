// ─── Internal Helper Functions ──────────────────────────────────────────────

pub(crate) fn sha256_short(input: &str) -> String {
    use sha2::{Sha256, Digest};
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    format!("{:x}", hasher.finalize())[..12].to_string()
}

pub(crate) fn chrono_now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

pub(crate) fn chrono_future_iso(days: i64) -> String {
    (chrono::Utc::now() + chrono::Duration::days(days)).to_rfc3339()
}
