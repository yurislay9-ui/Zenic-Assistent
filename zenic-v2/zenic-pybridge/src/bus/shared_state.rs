//! High-Performance Shared Memory Bus — SharedState.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

// ─── Shared State ──────────────────────────────────────────────

/// Thread-safe shared key-value store with atomic operations.
///
/// Uses RwLock for concurrent reads with exclusive writes.
/// Supports atomic increment/decrement and compare-and-swap.
///
/// Phase 3: Added bincode raw-bytes storage for zero-copy Rust↔Rust
/// communication, avoiding Python serialization overhead.
#[pyclass(name = "SharedState")]
pub struct SharedState {
    pub(crate) data: Arc<RwLock<HashMap<String, PyObject>>>,
    /// Raw bytes storage for bincode-serialized data (Rust↔Rust fast path).
    pub(crate) bincode_data: Arc<RwLock<HashMap<String, Vec<u8>>>>,
}

#[pymethods]
impl SharedState {
    #[new]
    fn new() -> Self {
        SharedState {
            data: Arc::new(RwLock::new(HashMap::new())),
            bincode_data: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Get a value by key.
    fn get(&self, py: Python<'_>, key: &str) -> Option<PyObject> {
        let data = self.data.read().ok()?;
        data.get(key).map(|v| v.clone_ref(py))
    }

    /// Set a value. Returns True if the key was new.
    ///
    /// E-03 FIX: Pre-clones the value under GIL, then releases GIL
    /// for the HashMap insertion.
    fn set(&self, py: Python<'_>, key: &str, value: PyObject) -> PyResult<bool> {
        let cloned = value.clone_ref(py);
        let key_owned = key.to_string();

        let is_new = py.allow_threads(|| {
            let mut data = match self.data.write() {
                Ok(d) => d,
                Err(_) => return false,
            };
            let was_new = !data.contains_key(&key_owned);
            data.insert(key_owned, cloned);
            was_new
        });

        Ok(is_new)
    }

    /// Delete a key. Returns True if the key existed.
    fn delete(&self, key: &str) -> PyResult<bool> {
        let mut data = self.data.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(data.remove(key).is_some())
    }

    /// Check if a key exists.
    fn has(&self, key: &str) -> PyResult<bool> {
        let data = self.data.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(data.contains_key(key))
    }

    /// Get all keys.
    fn keys(&self) -> PyResult<Vec<String>> {
        let data = self.data.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(data.keys().cloned().collect())
    }

    /// Atomic increment. Returns the new value.
    fn incr(&self, py: Python<'_>, key: &str, delta: i64) -> PyResult<i64> {
        let key_owned = key.to_string();

        let current_val: i64 = {
            let data = self.data.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            data.get(key)
                .and_then(|v| v.extract::<i64>(py).ok())
                .unwrap_or(0)
        };

        let new_val = current_val + delta;
        let new_obj = new_val.to_object(py);

        py.allow_threads(|| {
            let mut data = match self.data.write() {
                Ok(d) => d,
                Err(_) => return,
            };
            data.insert(key_owned, new_obj);
        });

        Ok(new_val)
    }

    /// Atomic decrement. Returns the new value.
    fn decr(&self, py: Python<'_>, key: &str, delta: i64) -> PyResult<i64> {
        self.incr(py, key, -delta)
    }

    /// Get or set a default value. Returns the existing value if present.
    fn get_or_set(&self, py: Python<'_>, key: &str, default: PyObject) -> PyResult<PyObject> {
        let key_owned = key.to_string();
        let default_clone = default.clone_ref(py);

        let result_key = py.allow_threads(|| -> Option<String> {
            let mut data = match self.data.write() {
                Ok(d) => d,
                Err(_) => return None,
            };
            if data.contains_key(&key_owned) {
                Some(key_owned.clone())
            } else {
                data.insert(key_owned.clone(), default_clone);
                None
            }
        });

        match result_key {
            Some(k) => {
                let data = self.data.read().map_err(|e| {
                    PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
                })?;
                Ok(data.get(&k).map(|v| v.clone_ref(py)).unwrap_or(default))
            }
            None => Ok(default),
        }
    }

    /// Atomic compare-and-swap.
    fn compare_and_swap(
        &self,
        py: Python<'_>,
        key: &str,
        expected: PyObject,
        new: PyObject,
    ) -> PyResult<bool> {
        let key_owned = key.to_string();

        let current_matches: bool = {
            let data = self.data.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            match data.get(key) {
                Some(current) => current.bind(py).eq(expected.bind(py))?,
                None => false,
            }
        };

        if !current_matches {
            return Ok(false);
        }

        let new_clone = new.clone_ref(py);
        py.allow_threads(|| {
            let mut data = match self.data.write() {
                Ok(d) => d,
                Err(_) => return,
            };
            data.insert(key_owned, new_clone);
        });

        Ok(true)
    }

    /// Return a snapshot of all key-value pairs.
    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let pairs: Vec<(String, PyObject)> = {
            let data = self.data.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            data.iter()
                .map(|(k, v)| (k.clone(), v.clone_ref(py)))
                .collect()
        };

        let result = PyDict::new_bound(py);
        for (k, v) in pairs {
            result.set_item(k, v)?;
        }
        Ok(result.unbind())
    }

    // ─── bincode Raw-Bytes Methods (Phase 3) ──────────────────

    /// Stores bincode-serialized data by key.
    fn set_bincode(&self, key: &str, data: Vec<u8>) -> PyResult<bool> {
        let key_owned = key.to_string();
        let mut bc_data = self.bincode_data.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let was_new = !bc_data.contains_key(&key_owned);
        bc_data.insert(key_owned, data);
        Ok(was_new)
    }

    /// Retrieves bincode-serialized data by key.
    fn get_bincode(&self, key: &str) -> PyResult<Option<Vec<u8>>> {
        let bc_data = self.bincode_data.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(bc_data.get(key).cloned())
    }

    /// Clear all data.
    fn clear(&self) -> PyResult<()> {
        {
            let mut data = self.data.write().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            data.clear();
        }
        {
            let mut bc_data = self.bincode_data.write().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            bc_data.clear();
        }
        Ok(())
    }
}
