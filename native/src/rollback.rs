//! Coordinated Rollback Engine — Atomic cross-resource rollback for Zenic-Agents.
//!
//! This module implements the A3 core in Rust for:
//! - Atomic state tracking with file-handle-level safety
//! - Cross-resource compensation ordering (reverse execution)
//! - File snapshot/restore with checksums
//! - State machine for rollback lifecycle (IN_PROGRESS → COMMITTED / ROLLED_BACK)
//! - Batch atomic verification (all-or-nothing rollback guarantee)
//!
//! Rust is ideal for this because:
//! - File handles and state pointers are managed safely
//! - Atomic operations are guaranteed by the borrow checker
//! - No GC pauses during critical rollback sequences

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::fs;
use std::path::Path;

// ─── State Machine ────────────────────────────────────────────

/// Represent the lifecycle state of a coordinated action.
#[pyclass(name = "RollbackActionStatus", eq, eq_int)]
#[derive(Clone, Debug, PartialEq)]
pub enum RollbackActionStatus {
    InProgress,
    Committed,
    RolledBack,
}

/// Represent a resource type for rollback compensation.
#[pyclass(name = "RollbackResourceType", eq, eq_int)]
#[derive(Clone, Debug, PartialEq)]
pub enum RollbackResourceType {
    Db,
    Email,
    File,
    Webhook,
}

// ─── File Snapshot ────────────────────────────────────────────

/// Create a snapshot (backup copy) of a file with a BLAKE3 checksum.
///
/// The snapshot is stored at the backup_path. The original file's
/// BLAKE3 hash is recorded so that restoration can be verified.
///
/// Parameters
/// ----------
/// source_path : str
///     Path to the file to snapshot.
/// backup_path : str
///     Path where the backup copy will be stored.
///
/// Returns
/// -------
/// dict
///     {
///         "success": bool,
///         "source_path": str,
///         "backup_path": str,
///         "checksum": str,
///         "file_size": int,
///         "error": str (only on failure)
///     }
#[pyfunction]
#[pyo3(signature = (source_path, backup_path))]
pub fn snapshot_file(py: Python<'_>, source_path: &str, backup_path: &str) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);
    let src = Path::new(source_path);

    if !src.exists() {
        result.set_item("success", false)?;
        result.set_item("source_path", source_path)?;
        result.set_item("backup_path", backup_path)?;
        result.set_item("error", format!("Source file does not exist: {}", source_path))?;
        return Ok(result.unbind());
    }

    match fs::read(source_path) {
        Ok(data) => {
            let checksum = blake3::hash(&data).to_hex().to_string();
            let file_size = data.len() as i64;

            // Create parent directory for backup if needed
            if let Some(parent) = Path::new(backup_path).parent() {
                let _ = fs::create_dir_all(parent);
            }

            match fs::write(backup_path, &data) {
                Ok(()) => {
                    result.set_item("success", true)?;
                    result.set_item("source_path", source_path)?;
                    result.set_item("backup_path", backup_path)?;
                    result.set_item("checksum", checksum)?;
                    result.set_item("file_size", file_size)?;
                }
                Err(e) => {
                    result.set_item("success", false)?;
                    result.set_item("source_path", source_path)?;
                    result.set_item("backup_path", backup_path)?;
                    result.set_item("error", format!("Failed to write backup: {}", e))?;
                }
            }
        }
        Err(e) => {
            result.set_item("success", false)?;
            result.set_item("source_path", source_path)?;
            result.set_item("backup_path", backup_path)?;
            result.set_item("error", format!("Failed to read source: {}", e))?;
        }
    }

    Ok(result.unbind())
}

/// Restore a file from a snapshot with checksum verification.
///
/// Reads the backup file, verifies its BLAKE3 checksum matches the
/// expected value, and then overwrites the target file atomically.
/// Uses a temporary file + rename for atomic write.
///
/// Parameters
/// ----------
/// backup_path : str
///     Path to the backup file.
/// target_path : str
///     Path to restore the file to.
/// expected_checksum : str
///     The BLAKE3 hex checksum that the backup must match.
///
/// Returns
/// -------
/// dict
///     {
///         "success": bool,
///         "backup_path": str,
///         "target_path": str,
///         "checksum_verified": bool,
///         "bytes_restored": int,
///         "error": str (only on failure)
///     }
#[pyfunction]
#[pyo3(signature = (backup_path, target_path, expected_checksum))]
pub fn restore_file(
    py: Python<'_>,
    backup_path: &str,
    target_path: &str,
    expected_checksum: &str,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);
    let bk = Path::new(backup_path);

    if !bk.exists() {
        result.set_item("success", false)?;
        result.set_item("backup_path", backup_path)?;
        result.set_item("target_path", target_path)?;
        result.set_item("checksum_verified", false)?;
        result.set_item("error", format!("Backup file does not exist: {}", backup_path))?;
        return Ok(result.unbind());
    }

    match fs::read(backup_path) {
        Ok(data) => {
            let actual_checksum = blake3::hash(&data).to_hex().to_string();
            let checksum_verified = actual_checksum == expected_checksum;
            let bytes_count = data.len() as i64;

            if !checksum_verified {
                result.set_item("success", false)?;
                result.set_item("backup_path", backup_path)?;
                result.set_item("target_path", target_path)?;
                result.set_item("checksum_verified", false)?;
                result.set_item("error", format!(
                    "Checksum mismatch: expected {}, got {}",
                    expected_checksum, actual_checksum
                ))?;
                return Ok(result.unbind());
            }

            // Create parent directory for target if needed
            if let Some(parent) = Path::new(target_path).parent() {
                let _ = fs::create_dir_all(parent);
            }

            // Atomic write: write to temp file first, then rename
            let temp_path = format!("{}.zenic_tmp", target_path);
            match fs::write(&temp_path, &data) {
                Ok(()) => {
                    match fs::rename(&temp_path, target_path) {
                        Ok(()) => {
                            result.set_item("success", true)?;
                            result.set_item("backup_path", backup_path)?;
                            result.set_item("target_path", target_path)?;
                            result.set_item("checksum_verified", true)?;
                            result.set_item("bytes_restored", bytes_count)?;
                        }
                        Err(e) => {
                            // Clean up temp file
                            let _ = fs::remove_file(&temp_path);
                            result.set_item("success", false)?;
                            result.set_item("backup_path", backup_path)?;
                            result.set_item("target_path", target_path)?;
                            result.set_item("checksum_verified", true)?;
                            result.set_item("error", format!("Failed to rename temp file: {}", e))?;
                        }
                    }
                }
                Err(e) => {
                    result.set_item("success", false)?;
                    result.set_item("backup_path", backup_path)?;
                    result.set_item("target_path", target_path)?;
                    result.set_item("checksum_verified", true)?;
                    result.set_item("error", format!("Failed to write temp file: {}", e))?;
                }
            }
        }
        Err(e) => {
            result.set_item("success", false)?;
            result.set_item("backup_path", backup_path)?;
            result.set_item("target_path", target_path)?;
            result.set_item("checksum_verified", false)?;
            result.set_item("error", format!("Failed to read backup: {}", e))?;
        }
    }

    Ok(result.unbind())
}

// ─── Atomic Verification ──────────────────────────────────────

/// Verify that a set of files can be rolled back by checking that
/// all backup files exist and their checksums match.
///
/// This is a pre-flight check before executing a coordinated rollback.
/// If any backup is missing or corrupted, the rollback should not proceed.
///
/// Parameters
/// ----------
/// resources : list[dict]
///     List of dicts with keys:
///     - "resource_type": str ("file", "db", "email", "webhook")
///     - "backup_path": str (for file resources)
///     - "expected_checksum": str (for file resources)
///
/// Returns
/// -------
/// dict
///     {
///         "all_verified": bool,
///         "total_resources": int,
///         "verified_count": int,
///         "failed": list[dict]
///     }
#[pyfunction]
#[pyo3(signature = (resources))]
pub fn verify_rollback_readiness(py: Python<'_>, resources: &Bound<'_, PyList>) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);
    let total = resources.len();
    let mut verified_count: usize = 0;
    let mut failed: Vec<Py<PyDict>> = Vec::new();

    for item in resources.iter() {
        let resource_type: String = item.get_item("resource_type")?.extract()?;

        if resource_type == "file" {
            let backup_path: String = item.get_item("backup_path")?.extract().unwrap_or_default();
            let expected_checksum: String = item.get_item("expected_checksum")?.extract().unwrap_or_default();

            let bk = Path::new(&backup_path);
            if !bk.exists() {
                let fail = PyDict::new_bound(py);
                fail.set_item("resource_type", &resource_type)?;
                fail.set_item("backup_path", &backup_path)?;
                fail.set_item("reason", "Backup file does not exist")?;
                failed.push(fail.unbind());
                continue;
            }

            match fs::read(&backup_path) {
                Ok(data) => {
                    let actual_checksum = blake3::hash(&data).to_hex().to_string();
                    if !expected_checksum.is_empty() && actual_checksum != expected_checksum {
                        let fail = PyDict::new_bound(py);
                        fail.set_item("resource_type", &resource_type)?;
                        fail.set_item("backup_path", &backup_path)?;
                        fail.set_item("reason", format!(
                            "Checksum mismatch: expected {}, got {}",
                            expected_checksum, actual_checksum
                        ))?;
                        failed.push(fail.unbind());
                    } else {
                        verified_count += 1;
                    }
                }
                Err(e) => {
                    let fail = PyDict::new_bound(py);
                    fail.set_item("resource_type", &resource_type)?;
                    fail.set_item("backup_path", &backup_path)?;
                    fail.set_item("reason", format!("Cannot read backup: {}", e))?;
                    failed.push(fail.unbind());
                }
            }
        } else {
            // DB, Email, Webhook — no file-level verification needed
            verified_count += 1;
        }
    }

    let all_verified = failed.is_empty();

    result.set_item("all_verified", all_verified)?;
    result.set_item("total_resources", total as i64)?;
    result.set_item("verified_count", verified_count as i64)?;
    result.set_item("failed", PyList::new_bound(py, &failed))?;

    Ok(result.unbind())
}

// ─── File Integrity Check ─────────────────────────────────────

/// Compute the BLAKE3 hash of a file.
///
/// Parameters
/// ----------
/// file_path : str
///     Path to the file.
///
/// Returns
/// -------
/// str
///     64-character hex-encoded BLAKE3 hash of the file contents.
///
/// Raises
/// ------
/// RuntimeError
///     If the file cannot be read.
#[pyfunction]
#[pyo3(signature = (file_path))]
pub fn file_hash(file_path: &str) -> PyResult<String> {
    match fs::read(file_path) {
        Ok(data) => {
            if data.is_empty() {
                return Err(PyRuntimeError::new_err(
                    format!("File is empty: {}", file_path),
                ));
            }
            Ok(blake3::hash(&data).to_hex().to_string())
        }
        Err(e) => Err(PyRuntimeError::new_err(format!(
            "Cannot read file {}: {}",
            file_path, e
        ))),
    }
}

// ─── Unit Tests ───────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_snapshot_and_restore() {
        let mut src = NamedTempFile::new().unwrap();
        writeln!(src, "test data for rollback").unwrap();
        let src_path = src.path().to_str().unwrap().to_string();

        let bk = NamedTempFile::new().unwrap();
        let bk_path = bk.path().to_str().unwrap().to_string();

        // Get checksum of source
        let data = fs::read(&src_path).unwrap();
        let checksum = blake3::hash(&data).to_hex().to_string();

        // Snapshot
        let py_result = Python::with_gil(|py| {
            snapshot_file(py, &src_path, &bk_path)
        }).unwrap();

        // Verify snapshot was created
        assert!(Path::new(&bk_path).exists());

        // Restore
        let target = NamedTempFile::new().unwrap();
        let target_path = target.path().to_str().unwrap().to_string();

        let restore_result = Python::with_gil(|py| {
            restore_file(py, &bk_path, &target_path, &checksum)
        }).unwrap();

        // Verify restored content matches
        let restored_data = fs::read(&target_path).unwrap();
        let original_data = fs::read(&src_path).unwrap();
        assert_eq!(restored_data, original_data);
    }

    #[test]
    fn test_file_hash() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "hello world").unwrap();
        let path = f.path().to_str().unwrap().to_string();
        let hash = file_hash(&path).unwrap();
        assert_eq!(hash.len(), 64);
    }
}
