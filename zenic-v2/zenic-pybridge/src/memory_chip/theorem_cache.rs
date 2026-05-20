//! Memory Chip — TheoremCache bincode serialization functions.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

/// Serialize a theorem cache entry to bincode bytes.
#[pyfunction]
pub fn theorem_cache_serialize(key: &str, value: &str, confidence: f64) -> PyResult<Vec<u8>> {
    let entry = (key.to_string(), value.to_string(), confidence);
    bincode::serialize(&entry)
        .map_err(|e| PyRuntimeError::new_err(format!("Bincode serialization error: {}", e)))
}

/// Deserialize a theorem cache entry from bincode bytes.
#[pyfunction]
pub fn theorem_cache_deserialize(data: &[u8]) -> PyResult<(String, String, f64)> {
    bincode::deserialize(data)
        .map_err(|e| PyRuntimeError::new_err(format!("Bincode deserialization error: {}", e)))
}
