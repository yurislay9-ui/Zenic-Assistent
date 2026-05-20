//! Unit tests for the rollback module.

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
        let data = std::fs::read(&src_path).unwrap();
        let checksum = blake3::hash(&data).to_hex().to_string();

        // Snapshot
        let py_result = pyo3::Python::with_gil(|py| {
            super::super::operations::snapshot_file(py, &src_path, &bk_path)
        }).unwrap();

        // Verify snapshot was created
        assert!(std::path::Path::new(&bk_path).exists());

        // Restore
        let target = NamedTempFile::new().unwrap();
        let target_path = target.path().to_str().unwrap().to_string();

        let restore_result = pyo3::Python::with_gil(|py| {
            super::super::operations::restore_file(py, &bk_path, &target_path, &checksum)
        }).unwrap();

        // Verify restored content matches
        let restored_data = std::fs::read(&target_path).unwrap();
        let original_data = std::fs::read(&src_path).unwrap();
        assert_eq!(restored_data, original_data);
    }

    #[test]
    fn test_file_hash() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "hello world").unwrap();
        let path = f.path().to_str().unwrap().to_string();
        let hash = super::super::operations::file_hash(&path).unwrap();
        assert_eq!(hash.len(), 64);
    }
}
