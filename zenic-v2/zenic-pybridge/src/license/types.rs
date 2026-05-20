//! License type definitions — LicenseTier, LicenseStatus, LicenseInfo, and helpers.

use pyo3::prelude::*;

use std::time::{SystemTime, UNIX_EPOCH};

// ═══════════════════════════════════════════════════════════════
//  LicenseTier
// ═══════════════════════════════════════════════════════════════

/// License tier levels — aligned with zenic-subscription Rust crate.
///
/// 5-tier model (all prices in USDT TRC20):
/// ====================== ======================================================
/// Variant                Meaning
/// ====================== ======================================================
/// Starter               $29/mo — basic pipeline, limited features
/// Business              $99/mo — full pipeline, advanced features (trial tier)
/// Enterprise            $299/mo — unlimited features, priority support
/// OnPremiseEnterprise   $799/mo + $2,000 setup — self-hosted, custom SLA
/// Trial                 14-day free trial with Business plan access
/// ====================== ======================================================
#[pyclass(name = "LicenseTier", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy)]
pub enum LicenseTier {
    Starter,
    Business,
    Enterprise,
    OnPremiseEnterprise,
    Trial,
}

impl LicenseTier {
    /// Return the Python-enum string value (e.g. ``"community"``).
    pub fn as_str(&self) -> &'static str {
        match self {
            LicenseTier::Starter => "starter",
            LicenseTier::Business => "business",
            LicenseTier::Enterprise => "enterprise",
            LicenseTier::OnPremiseEnterprise => "on_premise_enterprise",
            LicenseTier::Trial => "trial",
        }
    }

    /// Parse a tier string into a LicenseTier, defaulting to Community.
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "starter" | "community" | "free" => LicenseTier::Starter,
            "business" | "professional" | "pro" => LicenseTier::Business,
            "enterprise" => LicenseTier::Enterprise,
            "on_premise_enterprise" | "onpremiseenterprise" | "on-premise" | "on_premise" => LicenseTier::OnPremiseEnterprise,
            "whitelabel" | "white_label" | "white-label" => LicenseTier::OnPremiseEnterprise,
            "trial" => LicenseTier::Trial,
            _ => LicenseTier::Starter,
        }
    }
}

#[pymethods]
impl LicenseTier {
    /// Python ``str()`` → the enum value string.
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    /// Python ``repr()`` → ``LicenseTier.Community`` etc.
    fn __repr__(&self) -> String {
        match self {
            LicenseTier::Starter => "LicenseTier.Starter".into(),
            LicenseTier::Business => "LicenseTier.Business".into(),
            LicenseTier::Enterprise => "LicenseTier.Enterprise".into(),
            LicenseTier::OnPremiseEnterprise => "LicenseTier.OnPremiseEnterprise".into(),
            LicenseTier::Trial => "LicenseTier.Trial".into(),
        }
    }
}

// ═══════════════════════════════════════════════════════════════
//  LicenseStatus
// ═══════════════════════════════════════════════════════════════

/// Status of a license after verification.
///
/// ============ ==================================================
/// Variant      Meaning
/// ============ ==================================================
/// Valid        License is fully valid and active
/// Expired      License has expired past the grace period
/// Invalid      Signature or structure is invalid
/// Revoked      License has been revoked (kill switch, etc.)
/// GracePeriod  License expired but within grace period
/// ============ ==================================================
#[pyclass(name = "LicenseStatus", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy)]
pub enum LicenseStatus {
    Valid,
    Expired,
    Invalid,
    Revoked,
    GracePeriod,
}

impl LicenseStatus {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            LicenseStatus::Valid => "valid",
            LicenseStatus::Expired => "expired",
            LicenseStatus::Invalid => "invalid",
            LicenseStatus::Revoked => "revoked",
            LicenseStatus::GracePeriod => "grace_period",
        }
    }

    /// Parse a status string into a LicenseStatus, defaulting to Invalid.
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "valid" | "active" => LicenseStatus::Valid,
            "expired" => LicenseStatus::Expired,
            "invalid" => LicenseStatus::Invalid,
            "revoked" => LicenseStatus::Revoked,
            "grace_period" | "graceperiod" | "grace" => LicenseStatus::GracePeriod,
            _ => LicenseStatus::Invalid,
        }
    }
}

#[pymethods]
impl LicenseStatus {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("LicenseStatus.{}", self.as_str())
    }
}

// ═══════════════════════════════════════════════════════════════
//  LicenseInfo
// ═══════════════════════════════════════════════════════════════

/// Full license information structure.
///
/// All fields are **read-only** from Python (private Rust fields
/// exposed via ``#[getter]``). This prevents Python code from
/// tampering with license data after verification.
#[pyclass(name = "LicenseInfo")]
#[derive(Clone, Debug)]
pub struct LicenseInfo {
    license_key: String,
    tier: LicenseTier,
    holder: String,
    issued_at: i64,
    expires_at: i64,
    hardware_id: String,
    features: Vec<String>,
    max_users: u32,
    signature: String,
}

impl LicenseInfo {
    /// Create a canonical string representation for signing.
    ///
    /// The signature covers all fields except the signature itself,
    /// ensuring any modification invalidates the signature.
    pub fn to_signable_data(&self) -> String {
        let mut sorted_features = self.features.clone();
        sorted_features.sort();
        let parts = [
            self.license_key.as_str(),
            self.tier.as_str(),
            self.holder.as_str(),
            &self.issued_at.to_string(),
            &self.expires_at.to_string(),
            &sorted_features.join(","),
            &self.max_users.to_string(),
            self.hardware_id.as_str(),
        ];
        parts.join("|")
    }
}

#[pymethods]
impl LicenseInfo {
    /// Create a new LicenseInfo instance.
    #[new]
    #[pyo3(signature = (license_key, tier, holder, issued_at, expires_at, hardware_id="".to_string(), features=Vec::new(), max_users=1u32, signature="".to_string()))]
    fn new(
        license_key: String,
        tier: LicenseTier,
        holder: String,
        issued_at: i64,
        expires_at: i64,
        hardware_id: String,
        features: Vec<String>,
        max_users: u32,
        signature: String,
    ) -> Self {
        Self {
            license_key,
            tier,
            holder,
            issued_at,
            expires_at,
            hardware_id,
            features,
            max_users,
            signature,
        }
    }

    // ── Read-only getters ──────────────────────────────────────

    #[getter]
    fn license_key(&self) -> &str {
        &self.license_key
    }

    #[getter]
    fn tier(&self) -> LicenseTier {
        self.tier
    }

    #[getter]
    fn holder(&self) -> &str {
        &self.holder
    }

    #[getter]
    fn issued_at(&self) -> i64 {
        self.issued_at
    }

    #[getter]
    fn expires_at(&self) -> i64 {
        self.expires_at
    }

    #[getter]
    fn hardware_id(&self) -> &str {
        &self.hardware_id
    }

    #[getter]
    fn features(&self) -> Vec<String> {
        self.features.clone()
    }

    #[getter]
    fn max_users(&self) -> u32 {
        self.max_users
    }

    #[getter]
    fn signature(&self) -> &str {
        &self.signature
    }

    // ── Convenience helpers ────────────────────────────────────

    /// Check if the license has expired.
    fn is_expired(&self) -> bool {
        if self.expires_at == 0 {
            return false;
        }
        current_unix_timestamp() > self.expires_at
    }

    /// Check if this is a perpetual (non-expiring) license.
    fn is_perpetual(&self) -> bool {
        self.expires_at == 0
    }

    /// Get the number of days remaining until expiration.
    fn days_remaining(&self) -> Option<i64> {
        if self.is_perpetual() {
            return None;
        }
        let now = current_unix_timestamp();
        let remaining = (self.expires_at - now) / 86400;
        Some(remaining.max(0))
    }

    /// Check if a specific feature is enabled.
    fn has_feature(&self, feature: &str) -> bool {
        if self.features.iter().any(|f| f == "all") {
            return true;
        }
        self.features.iter().any(|f| f == feature)
    }

    fn __repr__(&self) -> String {
        format!(
            "LicenseInfo(license_key={:?}, tier={}, holder={:?}, \
             issued_at={}, expires_at={}, max_users={}, features={:?})",
            self.license_key,
            self.tier.as_str(),
            self.holder,
            self.issued_at,
            self.expires_at,
            self.max_users,
            self.features,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  Internal helpers
// ═══════════════════════════════════════════════════════════════

/// Current time as seconds since the Unix epoch.
pub(crate) fn current_unix_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}
