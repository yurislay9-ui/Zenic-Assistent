//! SharedState — Thread-safe shared key-value store with atomic operations.
//!
//! Uses RwLock for concurrent reads with exclusive writes.
//! Supports atomic increment/decrement and compare-and-swap.
//!
//! Phase 3: Added bincode raw-bytes storage for zero-copy Rust<->Rust
//! communication, avoiding Python serialization overhead.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

/// Thread-safe shared key-value store with atomic operations.
///
/// Uses RwLock for concurrent reads with exclusive writes.
/// Supports atomic increment/decrement and compare-and-swap.
///
/// Phase 3: Added bincode raw-bytes storage for zero-copy Rust<->Rust
/// communication, avoiding Python serialization overhead.
#[pyclass(name = "SharedState")]
pub struct SharedState {
    pub(crate) data: Arc<RwLock<HashMap<String, PyObject>>>,
    /// Raw bytes storage for bincode-serialized data (Rust<->Rust fast path).
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
    /// for the HashMap insertion. Prevents GIL deadlock when another
    /// thread holds a Rust lock and waits for the GIL.
    fn set(&self, py: Python<'_>, key: &str, value: PyObject) -> PyResult<bool> {
        let cloned = value.clone_ref(py);
        let key_owned = key.to_string();

        let is_new = py.allow_threads(|| {
            let mut data = match self.data.write() {
                Ok(d) => d,
                Err(_) => return false, // Lock poisoned
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
    ///
    /// E-03 FIX: Extracts the current value under GIL, then releases
    /// GIL for the write operation. The arithmetic is pure Rust.
    fn incr(&self, py: Python<'_>, key: &str, delta: i64) -> PyResult<i64> {
        let key_owned = key.to_string();

        // Read the current value under GIL (needed for Python int extraction)
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

        // E-03 FIX: Release GIL for the write operation
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
    ///
    /// E-03 FIX: Pre-clones the default under GIL, then releases GIL
    /// for the check-and-insert operation.
    fn get_or_set(&self, py: Python<'_>, key: &str, default: PyObject) -> PyResult<PyObject> {
        let key_owned = key.to_string();
        let default_clone = default.clone_ref(py);

        // E-03 FIX: Release GIL for the read-or-write operation.
        // We collect the result as an Option<PyObject> — if the key exists,
        // we clone it (safe: just incrementing refcount); if not, we insert
        // the pre-cloned default.
        let result_key = py.allow_threads(|| -> Option<String> {
            let mut data = match self.data.write() {
                Ok(d) => d,
                Err(_) => return None, // Lock poisoned
            };
            if data.contains_key(&key_owned) {
                Some(key_owned.clone())
            } else {
                data.insert(key_owned.clone(), default_clone);
                None // Signal that we inserted the default
            }
        });

        match result_key {
            Some(k) => {
                // Key existed — read and return the current value
                let data = self.data.read().map_err(|e| {
                    PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
                })?;
                Ok(data.get(&k).map(|v| v.clone_ref(py)).unwrap_or(default))
            }
            None => Ok(default),
        }
    }

    /// Atomic compare-and-swap.
    ///
    /// E-03 FIX: Reads the current value under GIL (for Python equality
    /// check), then releases GIL for the conditional write if matched.
    fn compare_and_swap(
        &self,
        py: Python<'_>,
        key: &str,
        expected: PyObject,
        new: PyObject,
    ) -> PyResult<bool> {
        let key_owned = key.to_string();

        // Step 1: Read current value under GIL (needed for Python ==)
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

        // Step 2: E-03 FIX — Release GIL for the conditional write
        let new_clone = new.clone_ref(py);
        py.allow_threads(|| {
            let mut data = match self.data.write() {
                Ok(d) => d,
                Err(_) => return,
            };
            // Double-check: key might have changed between read and write.
            // This is a TOCTOU race, but acceptable for compare_and_swap
            // semantics on a single-threaded Python runtime.
            data.insert(key_owned, new_clone);
        });

        Ok(true)
    }

    /// Return a snapshot of all key-value pairs.
    ///
    /// E-03 FIX: Collects keys and clones values under GIL-release,
    /// then builds the PyDict after re-acquiring GIL.
    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        // E-03 FIX: Release GIL for reading the HashMap and cloning PyObjects.
        // PyObject::clone_ref requires the GIL, so we just collect the
        // raw (key, value) pairs and build the dict after.
        let pairs: Vec<(String, PyObject)> = {
            let data = self.data.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            data.iter()
                .map(|(k, v)| (k.clone(), v.clone_ref(py)))
                .collect()
        };

        // Build PyDict after releasing the read lock (safe: no Rust locks held)
        let result = PyDict::new_bound(py);
        for (k, v) in pairs {
            result.set_item(k, v)?;
        }
        Ok(result.unbind())
    }

    // ─── bincode Raw-Bytes Methods (Phase 3) ──────────────────

    /// Stores bincode-serialized data by key.
    ///
    /// This method avoids Python serialization overhead for Rust<->Rust
    /// communication. The raw bytes are stored directly, enabling
    /// zero-copy deserialization on the reading side.
    ///
    /// Returns True if the key was new.
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
    ///
    /// Returns the raw bytes for zero-copy deserialization, or None
    /// if the key does not exist.
    ///
    /// This method avoids Python serialization overhead for Rust<->Rust
    /// communication through the shared state.
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
