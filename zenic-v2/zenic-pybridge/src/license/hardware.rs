//! Hardware fingerprint generation and binding verification.

use pyo3::prelude::*;

use std::fs;

use super::crypto::constant_time_compare;

/// Collect hardware identifiers cross-platform.
pub(crate) fn collect_hw_components() -> Vec<String> {
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
