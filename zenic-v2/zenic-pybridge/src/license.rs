//! Licensing & Anti-tampering — Security-critical operations for Zenic-Agents.
//!
//! This module implements the licensing system core in Rust for:
//! - Cryptographic license verification (HMAC-SHA256 signatures)
//! - Hardware fingerprint generation (BLAKE3-hashed system identifiers)
//! - Constant-time hardware binding comparison (timing-attack resistant)
//! - File integrity / anti-tampering checks (BLAKE3 hashes)
//! - Remote kill-switch connectivity check (TCP with timeout + grace period)
//!
//! Rust is ideal for these security-critical operations because:
//! - License verification is on the trust boundary — any bypass = revenue loss
//! - Constant-time comparison prevents timing side-channels
//! - BLAKE3 hashing is significantly faster than SHA-256 for fingerprints
//! - Anti-tampering checks must be tamper-resistant at the binary level
//! - The Rust type system enforces invariants that Python cannot

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use hmac::Hmac;
use sha2::Sha256;

use std::fs;
use std::io::Read;
use std::net::TcpStream;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

// ═══════════════════════════════════════════════════════════════
//  LicenseTier
// ═══════════════════════════════════════════════════════════════

/// License tier levels.
///
/// ============ ==================================================
/// Variant      Meaning
/// ============ ==================================================
/// Community    Free tier with basic features
/// Professional Professional tier with advanced features
/// Enterprise   Enterprise tier with all features
/// WhiteLabel   White-label / OEM redistribution license
/// ============ ==================================================
#[pyclass(name = "LicenseTier", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy)]
pub enum LicenseTier {
    Community,
    Professional,
    Enterprise,
    WhiteLabel,
}

impl LicenseTier {
    /// Return the Python-enum string value (e.g. ``"community"``).
    fn as_str(&self) -> &'static str {
        match self {
            LicenseTier::Community => "community",
            LicenseTier::Professional => "professional",
            LicenseTier::Enterprise => "enterprise",
            LicenseTier::WhiteLabel => "whitelabel",
        }
    }

    /// Parse a tier string into a LicenseTier, defaulting to Community.
    fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "community" | "free" => LicenseTier::Community,
            "professional" | "pro" => LicenseTier::Professional,
            "enterprise" => LicenseTier::Enterprise,
            "whitelabel" | "white_label" | "white-label" => LicenseTier::WhiteLabel,
            _ => LicenseTier::Community,
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
            LicenseTier::Community => "LicenseTier.Community".into(),
            LicenseTier::Professional => "LicenseTier.Professional".into(),
            LicenseTier::Enterprise => "LicenseTier.Enterprise".into(),
            LicenseTier::WhiteLabel => "LicenseTier.WhiteLabel".into(),
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
    fn as_str(&self) -> &'static str {
        match self {
            LicenseStatus::Valid => "valid",
            LicenseStatus::Expired => "expired",
            LicenseStatus::Invalid => "invalid",
            LicenseStatus::Revoked => "revoked",
            LicenseStatus::GracePeriod => "grace_period",
        }
    }

    /// Parse a status string into a LicenseStatus, defaulting to Invalid.
    fn from_str(s: &str) -> Self {
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
fn current_unix_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64
}

/// Constant-time comparison of two byte slices.
fn constant_time_compare(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut result: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        result |= x ^ y;
    }
    result == 0
}

/// Compute HMAC-SHA256 of data with the given secret key.
fn hmac_sha256(secret: &[u8], data: &[u8]) -> [u8; 32] {
    use hmac::Mac;
    let mut mac = Hmac::<Sha256>::new_from_slice(secret)
        .expect("HMAC can accept any key size");
    mac.update(data);
    mac.finalize().into_bytes().into()
}

/// Parse a URL string to extract (host, port).
fn parse_host_port(url: &str) -> Option<(String, u16)> {
    let url = url.trim();
    if url.is_empty() {
        return None;
    }

    let (scheme, rest) = if url.starts_with("https://") {
        ("https", &url[8..])
    } else if url.starts_with("http://") {
        ("http", &url[7..])
    } else {
        ("http", url)
    };

    let host_port = rest.split('/').next().unwrap_or(rest);
    let default_port: u16 = if scheme == "https" { 443 } else { 80 };

    // Handle [IPv6]:port format
    if host_port.starts_with('[') {
        if let Some(bracket_end) = host_port.find(']') {
            let host = &host_port[1..bracket_end];
            let remainder = &host_port[bracket_end + 1..];
            let port = if remainder.starts_with(':') {
                remainder[1..].parse().unwrap_or(default_port)
            } else {
                default_port
            };
            return Some((host.to_string(), port));
        }
    }

    // Handle host:port format
    if let Some(colon_pos) = host_port.rfind(':') {
        let host = &host_port[..colon_pos];
        let port_str = &host_port[colon_pos + 1..];
        if port_str.chars().all(|c| c.is_ascii_digit()) && !port_str.is_empty() {
            let port = port_str.parse().unwrap_or(default_port);
            return Some((host.to_string(), port));
        }
    }

    Some((host_port.to_string(), default_port))
}

/// Collect hardware identifiers cross-platform.
fn collect_hw_components() -> Vec<String> {
    let mut components: Vec<String> = Vec::new();

    // 1. Hostname
    #[cfg(target_family = "unix")]
    {
        if let Ok(host) = std::env::var("HOSTNAME") {
            components.push(format!("host:{}", host));
        } else if let Ok(data) = fs::read_to_string("/etc/hostname") {
            components.push(format!("host:{}", data.trim()));
        }
    }

    #[cfg(target_family = "windows")]
    {
        if let Ok(host) = std::env::var("COMPUTERNAME") {
            components.push(format!("host:{}", host));
        }
    }

    // 2. CPU count
    if let Ok(count) = std::thread::available_parallelism() {
        components.push(format!("cpu:{}", count.get()));
    }

    // 3. Total memory (platform-specific)
    #[cfg(target_os = "linux")]
    {
        if let Ok(data) = fs::read_to_string("/proc/meminfo") {
            for line in data.lines() {
                if line.starts_with("MemTotal:") {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 2 {
                        components.push(format!("mem:{}", parts[1]));
                    }
                    break;
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        if let Ok(output) = std::process::Command::new("sysctl")
            .args(["-n", "hw.memsize"])
            .output()
        {
            if output.status.success() {
                let mem = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !mem.is_empty() {
                    components.push(format!("mem:{}", mem));
                }
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        if let Ok(output) = std::process::Command::new("wmic")
            .args(["OS", "get", "TotalVisibleMemorySize", "/value"])
            .output()
        {
            if output.status.success() {
                let mem_str = String::from_utf8_lossy(&output.stdout);
                for line in mem_str.lines() {
                    if line.starts_with("TotalVisibleMemorySize=") {
                        let val = line.split('=').nth(1).unwrap_or("").trim();
                        if !val.is_empty() {
                            components.push(format!("mem:{}", val));
                        }
                        break;
                    }
                }
            }
        }
    }

    // 4. Disk size (root filesystem)
    #[cfg(target_family = "unix")]
    {
        if let Ok(output) = std::process::Command::new("df")
            .args(["-B1", "/"])
            .output()
        {
            if output.status.success() {
                let df_str = String::from_utf8_lossy(&output.stdout);
                for line in df_str.lines().skip(1) {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if parts.len() >= 2 {
                        components.push(format!("disk:{}", parts[1]));
                        break;
                    }
                }
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        if let Ok(output) = std::process::Command::new("wmic")
            .args(["logicaldisk", "get", "size", "/value"])
            .output()
        {
            if output.status.success() {
                let disk_str = String::from_utf8_lossy(&output.stdout);
                for line in disk_str.lines() {
                    if line.starts_with("Size=") {
                        let val = line.split('=').nth(1).unwrap_or("").trim();
                        if !val.is_empty() {
                            components.push(format!("disk:{}", val));
                            break;
                        }
                    }
                }
            }
        }
    }

    // 5. MAC address
    #[cfg(target_os = "linux")]
    {
        if let Ok(entries) = fs::read_dir("/sys/class/net") {
            for entry in entries.flatten() {
                let name = entry.file_name();
                let name_str = name.to_string_lossy();
                if name_str == "lo" {
                    continue;
                }
                let addr_path = format!("/sys/class/net/{}/address", name_str);
                if let Ok(mac) = fs::read_to_string(&addr_path) {
                    let mac = mac.trim().to_string();
                    if !mac.is_empty() && mac != "00:00:00:00:00:00" {
                        components.push(format!("mac:{}", mac));
                        break;
                    }
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        if let Ok(output) = std::process::Command::new("ifconfig").output() {
            if output.status.success() {
                let ifconfig = String::from_utf8_lossy(&output.stdout);
                for line in ifconfig.lines() {
                    let line = line.trim();
                    if line.starts_with("ether ") {
                        let mac = line[6..].trim().to_string();
                        if mac != "00:00:00:00:00:00" {
                            components.push(format!("mac:{}", mac));
                            break;
                        }
                    }
                }
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        if let Ok(output) = std::process::Command::new("getmac").output() {
            if output.status.success() {
                let macs = String::from_utf8_lossy(&output.stdout);
                for line in macs.lines() {
                    let mac = line.trim().replace('-', ":");
                    if mac.len() == 17 && mac != "00:00:00:00:00:00" {
                        components.push(format!("mac:{}", mac));
                        break;
                    }
                }
            }
        }
    }

    // Fallback if nothing collected
    if components.is_empty() {
        components.push("default-hw".to_string());
    }

    components
}

/// Encode bytes as a hex string (lowercase).
fn hex_encode(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}

/// Decode a hex string to bytes.
fn hex_decode(hex: &str) -> Result<Vec<u8>, String> {
    let hex = hex.trim();
    if hex.len() % 2 != 0 {
        return Err("Hex string has odd length".to_string());
    }
    (0..hex.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&hex[i..i + 2], 16)
                .map_err(|e| format!("Invalid hex at position {}: {}", i, e))
        })
        .collect()
}

// ═══════════════════════════════════════════════════════════════
//  PyO3-exposed functions
// ═══════════════════════════════════════════════════════════════

/// Verify a license JSON payload against a cryptographic key.
///
/// Parameters
/// ----------
/// license_json : str
///     JSON string containing the license data.
/// public_key : str
///     HMAC secret key for signature verification.
///
/// Returns
/// -------
/// dict
///     ``{"is_valid": bool, "status": str, "tier": str,
///      "expires_at": int, "days_remaining": int, "error": str}``
#[pyfunction]
#[pyo3(signature = (license_json, public_key))]
pub fn verify_license(
    py: Python<'_>,
    license_json: &str,
    public_key: &str,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    // 1. Parse JSON
    let parsed: serde_json::Value = match serde_json::from_str(license_json) {
        Ok(v) => v,
        Err(e) => {
            result.set_item("is_valid", false)?;
            result.set_item("status", "invalid")?;
            result.set_item("tier", "community")?;
            result.set_item("expires_at", 0)?;
            result.set_item("days_remaining", 0)?;
            result.set_item("error", format!("JSON parse error: {}", e))?;
            return Ok(result.unbind());
        }
    };

    // Helper closures
    let get_str = |obj: &serde_json::Value, keys: &[&str]| -> String {
        for key in keys {
            if let Some(val) = obj.get(key).and_then(|v| v.as_str()) {
                return val.to_string();
            }
        }
        String::new()
    };

    let get_i64 = |obj: &serde_json::Value, key: &str| -> i64 {
        obj.get(key).and_then(|v| v.as_i64()).unwrap_or(0)
    };

    let get_u32 = |obj: &serde_json::Value, key: &str| -> u32 {
        obj.get(key).and_then(|v| v.as_u64()).unwrap_or(1) as u32
    };

    // 2. Extract fields
    let license_key = get_str(&parsed, &["license_key", "license_id"]);
    let tier_str = get_str(&parsed, &["tier"]);
    let holder = get_str(&parsed, &["holder", "issued_to"]);
    let issued_at = get_i64(&parsed, "issued_at");
    let expires_at = get_i64(&parsed, "expires_at");
    let hardware_id = get_str(&parsed, &["hardware_id"]);
    let max_users = get_u32(&parsed, "max_users");
    let signature = get_str(&parsed, &["signature"]);

    let features: Vec<String> = parsed
        .get("features")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let tier = LicenseTier::from_str(&tier_str);

    // 3. Reconstruct canonical signable data
    let mut sorted_features = features.clone();
    sorted_features.sort();
    let signable_parts = [
        license_key.as_str(),
        tier.as_str(),
        holder.as_str(),
        &issued_at.to_string(),
        &expires_at.to_string(),
        &sorted_features.join(","),
        &max_users.to_string(),
        hardware_id.as_str(),
    ];
    let signable_data = signable_parts.join("|");

    // 4. Verify HMAC-SHA256 signature
    let expected_hmac = hmac_sha256(public_key.as_bytes(), signable_data.as_bytes());
    let expected_hex = hex_encode(&expected_hmac);

    let sig_valid = if signature.len() == expected_hex.len() {
        constant_time_compare(signature.as_bytes(), expected_hex.as_bytes())
    } else {
        match hex_decode(&signature) {
            Ok(sig_bytes) => constant_time_compare(&sig_bytes, &expected_hmac),
            Err(_) => false,
        }
    };

    if !sig_valid {
        result.set_item("is_valid", false)?;
        result.set_item("status", "invalid")?;
        result.set_item("tier", tier.as_str())?;
        result.set_item("expires_at", expires_at)?;
        result.set_item("days_remaining", 0)?;
        result.set_item("error", "Invalid signature")?;
        return Ok(result.unbind());
    }

    // 5. Check expiration
    let now = current_unix_timestamp();
    let (is_valid, status, days_remaining) = if expires_at == 0 {
        (true, "valid", i64::MAX)
    } else if now > expires_at {
        let hours_expired = (now - expires_at) / 3600;
        if hours_expired <= 72 {
            let days_rem = ((expires_at - now) / 86400).max(0);
            (true, "grace_period", days_rem)
        } else {
            (false, "expired", 0)
        }
    } else {
        let days_rem = (expires_at - now) / 86400;
        (true, "valid", days_rem)
    };

    result.set_item("is_valid", is_valid)?;
    result.set_item("status", status)?;
    result.set_item("tier", tier.as_str())?;
    result.set_item("expires_at", expires_at)?;
    result.set_item("days_remaining", days_remaining)?;
    result.set_item("error", "")?;

    Ok(result.unbind())
}

/// Generate a hardware fingerprint from system identifiers.
///
/// Combines hostname, CPU count, total memory, disk size, and MAC address
/// into a single BLAKE3 hash for hardware binding.
///
/// Returns
/// -------
/// str
///     64-character hex-encoded BLAKE3 hardware fingerprint.
#[pyfunction]
pub fn generate_hardware_fingerprint() -> PyResult<String> {
    let components = collect_hw_components();
    let combined = components.join("|");
    let hash = blake3::hash(combined.as_bytes());
    Ok(hash.to_hex().to_string())
}

/// Verify that the current hardware matches a stored hardware fingerprint.
///
/// Parameters
/// ----------
/// license_hw_id : str
///     The hardware fingerprint stored in the license.
///
/// Returns
/// -------
/// bool
///     True if the current hardware matches the stored fingerprint.
#[pyfunction]
#[pyo3(signature = (license_hw_id))]
pub fn verify_hardware_binding(license_hw_id: &str) -> PyResult<bool> {
    let current_fp = generate_hardware_fingerprint()?;
    Ok(constant_time_compare(
        current_fp.as_bytes(),
        license_hw_id.as_bytes(),
    ))
}

/// Check files for tampering by comparing current BLAKE3 hashes with expected values.
///
/// Parameters
/// ----------
/// check_paths : list[str]
///     File paths to check.
/// expected_hashes : list[str]
///     Expected BLAKE3 hex hashes for each path (same order).
///
/// Returns
/// -------
/// dict
///     ``{"is_tampered": bool, "checked_files": int,
///      "tampered_files": list[str], "details": list[dict]}``
#[pyfunction]
#[pyo3(signature = (check_paths, expected_hashes))]
pub fn check_tampering(
    py: Python<'_>,
    check_paths: Vec<String>,
    expected_hashes: Vec<String>,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    if check_paths.len() != expected_hashes.len() {
        return Err(PyValueError::new_err(
            "check_paths and expected_hashes must have the same length",
        ));
    }

    let mut tampered_files: Vec<String> = Vec::new();
    let details = PyList::empty_bound(py);
    let mut checked_count: i32 = 0;

    for (path, expected_hash) in check_paths.iter().zip(expected_hashes.iter()) {
        checked_count += 1;
        let detail = PyDict::new_bound(py);

        detail.set_item("path", path)?;
        detail.set_item("expected_hash", expected_hash)?;

        match fs::read(path) {
            Ok(data) => {
                let current_hash = blake3::hash(&data).to_hex().to_string();
                detail.set_item("current_hash", &current_hash)?;

                let is_tampered = !constant_time_compare(
                    current_hash.as_bytes(),
                    expected_hash.as_bytes(),
                );
                detail.set_item("is_tampered", is_tampered)?;
                detail.set_item("error", "")?;

                if is_tampered {
                    tampered_files.push(path.clone());
                }
            }
            Err(e) => {
                detail.set_item("current_hash", "")?;
                detail.set_item("is_tampered", true)?;
                detail.set_item("error", e.to_string())?;
                tampered_files.push(path.clone());
            }
        }

        details.append(detail.as_any())?;
    }

    result.set_item("is_tampered", !tampered_files.is_empty())?;
    result.set_item("checked_files", checked_count)?;
    result.set_item("tampered_files", tampered_files)?;
    result.set_item("details", details)?;

    Ok(result.unbind())
}

/// Sign data using HMAC-SHA256.
///
/// Parameters
/// ----------
/// data : str
///     The data to sign.
/// secret_key : str
///     The secret key for the HMAC.
///
/// Returns
/// -------
/// str
///     Hex-encoded HMAC-SHA256 signature.
#[pyfunction]
#[pyo3(signature = (data, secret_key))]
pub fn sign_data(data: &str, secret_key: &str) -> PyResult<String> {
    let mac = hmac_sha256(secret_key.as_bytes(), data.as_bytes());
    Ok(hex_encode(&mac))
}

/// Verify an HMAC-SHA256 signature using constant-time comparison.
///
/// Parameters
/// ----------
/// data : str
///     The original data that was signed.
/// signature : str
///     The hex-encoded signature to verify.
/// secret_key : str
///     The secret key used for signing.
///
/// Returns
/// -------
/// bool
///     True if the signature is valid.
#[pyfunction]
#[pyo3(signature = (data, signature, secret_key))]
pub fn verify_signature(data: &str, signature: &str, secret_key: &str) -> PyResult<bool> {
    let expected = hmac_sha256(secret_key.as_bytes(), data.as_bytes());
    let expected_hex = hex_encode(&expected);

    if signature.len() == expected_hex.len() {
        return Ok(constant_time_compare(
            signature.as_bytes(),
            expected_hex.as_bytes(),
        ));
    }

    match hex_decode(signature) {
        Ok(sig_bytes) => Ok(constant_time_compare(&sig_bytes, &expected)),
        Err(_) => Ok(false),
    }
}

/// Check the remote kill-switch endpoint.
///
/// Performs a TCP connectivity check to the remote URL. If the server is
/// reachable, attempts a minimal HTTP GET to read the response. If the
/// server is unreachable, a grace period is applied.
///
/// Parameters
/// ----------
/// remote_url : str
///     The kill-switch endpoint URL.
/// license_key : str
///     The license key to identify the client.
/// timeout_secs : int
///     Connection timeout in seconds (default: 5).
///
/// Returns
/// -------
/// dict
///     ``{"is_active": bool, "should_disable": bool, "message": str}``
#[pyfunction]
#[pyo3(signature = (remote_url, license_key, timeout_secs=5u64))]
pub fn check_kill_switch(
    py: Python<'_>,
    remote_url: &str,
    license_key: &str,
    timeout_secs: u64,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    // Empty URL = no kill switch configured
    if remote_url.trim().is_empty() {
        result.set_item("is_active", true)?;
        result.set_item("should_disable", false)?;
        result.set_item("message", "No kill switch URL configured, license is active")?;
        return Ok(result.unbind());
    }

    // Parse the URL to extract host and port
    let (host, port) = match parse_host_port(remote_url) {
        Some(hp) => hp,
        None => {
            result.set_item("is_active", false)?;
            result.set_item("should_disable", false)?;
            result.set_item("message", format!("Invalid kill switch URL: {}", remote_url))?;
            return Ok(result.unbind());
        }
    };

    // Try TCP connection with timeout
    let addr = format!("{}:{}", host, port);
    let timeout = Duration::from_secs(timeout_secs);

    match TcpStream::connect_timeout(
        &addr.parse().map_err(|e: std::net::AddrParseError| {
            PyValueError::new_err(format!("Invalid address '{}': {}", addr, e))
        })?,
        timeout,
    ) {
        Ok(stream) => {
            // Server is reachable — attempt a minimal HTTP GET
            let response = perform_simple_http_get(
                &stream, &host, remote_url, license_key, timeout,
            );

            match response {
                Ok(body) => {
                    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&body) {
                        let is_active = parsed
                            .get("active")
                            .or_else(|| parsed.get("is_active"))
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true);

                        let should_disable = parsed
                            .get("should_disable")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);

                        let message = parsed
                            .get("message")
                            .and_then(|v| v.as_str())
                            .unwrap_or("Kill switch check completed")
                            .to_string();

                        result.set_item("is_active", is_active)?;
                        result.set_item("should_disable", should_disable)?;
                        result.set_item("message", message)?;
                    } else {
                        result.set_item("is_active", true)?;
                        result.set_item("should_disable", false)?;
                        result.set_item("message", "Server reachable, license appears active")?;
                    }
                }
                Err(_) => {
                    result.set_item("is_active", true)?;
                    result.set_item("should_disable", false)?;
                    result.set_item(
                        "message",
                        "Server reachable but could not read response, license assumed active",
                    )?;
                }
            }
        }
        Err(_) => {
            // Server unreachable — apply grace period
            result.set_item("is_active", false)?;
            result.set_item("should_disable", false)?;
            result.set_item(
                "message",
                format!("Kill switch server unreachable ({}), grace period active", addr),
            )?;
        }
    }

    Ok(result.unbind())
}

/// Perform a simple HTTP GET request over an established TCP stream.
fn perform_simple_http_get(
    stream: &TcpStream,
    host: &str,
    path_url: &str,
    license_key: &str,
    timeout: Duration,
) -> Result<String, std::io::Error> {
    use std::io::{BufRead, BufReader, Write};

    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;

    // Extract path from URL
    let path = if path_url.starts_with("http://") || path_url.starts_with("https://") {
        let after_scheme = if path_url.starts_with("http://") {
            &path_url[7..]
        } else {
            &path_url[8..]
        };
        if let Some(slash_pos) = after_scheme.find('/') {
            &after_scheme[slash_pos..]
        } else {
            "/"
        }
    } else {
        "/"
    };

    let request = format!(
        "GET {}?license_key={} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\nAccept: application/json\r\n\r\n",
        path, license_key, host
    );

    let mut stream = stream.try_clone()?;
    stream.write_all(request.as_bytes())?;

    let mut reader = BufReader::new(stream);
    let mut body = String::new();

    // Skip HTTP headers
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) | Err(_) => break,
            Ok(_) => {
                if line == "\r\n" || line == "\n" {
                    break;
                }
            }
        }
    }

    reader.read_to_string(&mut body)?;
    Ok(body)
}

// ═══════════════════════════════════════════════════════════════
//  Unit tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_license_tier_str_roundtrip() {
        assert_eq!(LicenseTier::Community.as_str(), "community");
        assert_eq!(LicenseTier::Professional.as_str(), "professional");
        assert_eq!(LicenseTier::Enterprise.as_str(), "enterprise");
        assert_eq!(LicenseTier::WhiteLabel.as_str(), "whitelabel");
    }

    #[test]
    fn test_license_tier_from_str() {
        assert_eq!(LicenseTier::from_str("community"), LicenseTier::Community);
        assert_eq!(LicenseTier::from_str("free"), LicenseTier::Community);
        assert_eq!(LicenseTier::from_str("professional"), LicenseTier::Professional);
        assert_eq!(LicenseTier::from_str("pro"), LicenseTier::Professional);
        assert_eq!(LicenseTier::from_str("enterprise"), LicenseTier::Enterprise);
        assert_eq!(LicenseTier::from_str("whitelabel"), LicenseTier::WhiteLabel);
        assert_eq!(LicenseTier::from_str("unknown"), LicenseTier::Community);
    }

    #[test]
    fn test_license_status_str_roundtrip() {
        assert_eq!(LicenseStatus::Valid.as_str(), "valid");
        assert_eq!(LicenseStatus::Expired.as_str(), "expired");
        assert_eq!(LicenseStatus::Invalid.as_str(), "invalid");
        assert_eq!(LicenseStatus::Revoked.as_str(), "revoked");
        assert_eq!(LicenseStatus::GracePeriod.as_str(), "grace_period");
    }

    #[test]
    fn test_license_status_from_str() {
        assert_eq!(LicenseStatus::from_str("valid"), LicenseStatus::Valid);
        assert_eq!(LicenseStatus::from_str("active"), LicenseStatus::Valid);
        assert_eq!(LicenseStatus::from_str("expired"), LicenseStatus::Expired);
        assert_eq!(LicenseStatus::from_str("invalid"), LicenseStatus::Invalid);
        assert_eq!(LicenseStatus::from_str("revoked"), LicenseStatus::Revoked);
        assert_eq!(LicenseStatus::from_str("grace_period"), LicenseStatus::GracePeriod);
    }

    #[test]
    fn test_signable_data_deterministic() {
        let info = LicenseInfo {
            license_key: "zl-abc123".to_string(),
            tier: LicenseTier::Professional,
            holder: "Test Org".to_string(),
            issued_at: 1700000000,
            expires_at: 1800000000,
            hardware_id: "hw123".to_string(),
            features: vec!["b".to_string(), "a".to_string()],
            max_users: 5,
            signature: String::new(),
        };
        let data = info.to_signable_data();
        assert!(data.contains("a,b"));
        assert!(data.starts_with("zl-abc123|professional|Test Org|"));
    }

    #[test]
    fn test_sign_and_verify_roundtrip() {
        let data = "test data to sign";
        let secret = "super-secret-key";

        let sig = hmac_sha256(secret.as_bytes(), data.as_bytes());
        let sig_hex = hex_encode(&sig);

        let expected = hmac_sha256(secret.as_bytes(), data.as_bytes());
        let expected_hex = hex_encode(&expected);
        assert!(constant_time_compare(sig_hex.as_bytes(), expected_hex.as_bytes()));

        let wrong = hmac_sha256(b"wrong-key", data.as_bytes());
        let wrong_hex = hex_encode(&wrong);
        assert!(!constant_time_compare(sig_hex.as_bytes(), wrong_hex.as_bytes()));
    }

    #[test]
    fn test_constant_time_compare() {
        assert!(constant_time_compare(b"hello", b"hello"));
        assert!(!constant_time_compare(b"hello", b"world"));
        assert!(!constant_time_compare(b"hello", b"helloworld"));
    }

    #[test]
    fn test_hex_encode_decode_roundtrip() {
        let bytes: Vec<u8> = (0..32).collect();
        let encoded = hex_encode(&bytes);
        assert_eq!(encoded.len(), 64);
        let decoded = hex_decode(&encoded).unwrap();
        assert_eq!(bytes, decoded);
    }

    #[test]
    fn test_parse_host_port() {
        assert_eq!(
            parse_host_port("http://example.com/api/check"),
            Some(("example.com".to_string(), 80))
        );
        assert_eq!(
            parse_host_port("https://example.com:8443/api"),
            Some(("example.com".to_string(), 8443))
        );
        assert_eq!(
            parse_host_port("example.com:9090"),
            Some(("example.com".to_string(), 9090))
        );
        assert_eq!(parse_host_port(""), None);
    }

    #[test]
    fn test_license_info_has_feature() {
        let info = LicenseInfo {
            license_key: "test".to_string(),
            tier: LicenseTier::Enterprise,
            holder: "Test".to_string(),
            issued_at: 0,
            expires_at: 0,
            hardware_id: String::new(),
            features: vec!["all".to_string()],
            max_users: 1,
            signature: String::new(),
        };
        assert!(info.has_feature("anything"));
        assert!(info.has_feature("everything"));
    }

    #[test]
    fn test_license_info_perpetual() {
        let info = LicenseInfo {
            license_key: "test".to_string(),
            tier: LicenseTier::Enterprise,
            holder: "Test".to_string(),
            issued_at: 0,
            expires_at: 0,
            hardware_id: String::new(),
            features: vec![],
            max_users: 1,
            signature: String::new(),
        };
        assert!(info.is_perpetual());
        assert!(!info.is_expired());
        assert_eq!(info.days_remaining(), None);
    }

    #[test]
    fn test_hardware_fingerprint_deterministic() {
        let fp1 = generate_hardware_fingerprint().unwrap();
        let fp2 = generate_hardware_fingerprint().unwrap();
        assert_eq!(fp1, fp2);
        assert_eq!(fp1.len(), 64); // BLAKE3 hex = 64 chars
    }
}
