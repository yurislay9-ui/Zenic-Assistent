//! RingBuffer — Fixed-size circular buffer for event streams.
//!
//! Pre-allocated with a fixed capacity. When full, the oldest
//! item is overwritten on push. O(1) push and pop operations.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use std::collections::VecDeque;
use std::sync::{Arc, RwLock};

/// Fixed-size circular buffer for event streams.
///
/// Pre-allocated with a fixed capacity. When full, the oldest
/// item is overwritten on push. O(1) push and pop operations.
#[pyclass(name = "RingBuffer")]
pub struct RingBuffer {
    pub(crate) buffer: Arc<RwLock<VecDeque<PyObject>>>,
    pub(crate) capacity: usize,
}

#[pymethods]
impl RingBuffer {
    #[new]
    fn new(capacity: usize) -> Self {
        RingBuffer {
            buffer: Arc::new(RwLock::new(VecDeque::with_capacity(capacity))),
            capacity: if capacity == 0 { 1024 } else { capacity },
        }
    }

    /// Push an item. Returns False if it overwrote the oldest item.
    fn push(&self, py: Python<'_>, item: PyObject) -> PyResult<bool> {
        let mut buf = self.buffer.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let was_full = buf.len() >= self.capacity;
        if was_full {
            buf.pop_front();
        }
        buf.push_back(item.clone_ref(py));
        Ok(!was_full)
    }

    /// Pop the oldest item. Returns None if empty.
    fn pop(&self, py: Python<'_>) -> PyResult<Option<PyObject>> {
        let mut buf = self.buffer.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(buf.pop_front().map(|v| v.clone_ref(py)))
    }

    /// Peek at the oldest item without removing it.
    fn peek(&self, py: Python<'_>) -> PyResult<Option<PyObject>> {
        let buf = self.buffer.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(buf.front().map(|v| v.clone_ref(py)))
    }

    /// Current number of items.
    fn len(&self) -> PyResult<usize> {
        let buf = self.buffer.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(buf.len())
    }

    /// Check if the buffer is empty.
    fn is_empty(&self) -> PyResult<bool> {
        let buf = self.buffer.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(buf.is_empty())
    }

    /// Check if the buffer is full.
    fn is_full(&self) -> PyResult<bool> {
        let buf = self.buffer.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(buf.len() >= self.capacity)
    }

    /// Maximum capacity.
    fn capacity(&self) -> usize {
        self.capacity
    }

    /// Return all items in order (oldest first).
    fn to_list(&self, py: Python<'_>) -> PyResult<Vec<PyObject>> {
        let buf = self.buffer.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(buf.iter().map(|v| v.clone_ref(py)).collect())
    }

    /// Clear the buffer.
    fn clear(&self) -> PyResult<()> {
        let mut buf = self.buffer.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        buf.clear();
        Ok(())
    }

    /// Get the item at a specific index (0 = oldest).
    fn __getitem__(&self, py: Python<'_>, index: isize) -> PyResult<PyObject> {
        let buf = self.buffer.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let len = buf.len() as isize;
        let idx = if index < 0 { len + index } else { index };
        if idx < 0 || idx >= len {
            return Err(PyRuntimeError::new_err(format!(
                "Index {} out of range (len={})", index, len
            )));
        }
        Ok(buf[idx as usize].clone_ref(py))
    }
}
