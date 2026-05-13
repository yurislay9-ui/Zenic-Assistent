//! High-Performance Shared Memory Bus for Zenic-Agents.
//!
//! Provides fast inter-agent communication with:
//! - SharedMemoryBus: pub/sub topic-based message bus
//! - SharedState: thread-safe key-value store with atomic operations
//! - RingBuffer: fixed-size circular buffer for event streams
//!
//! Rust is ideal for this because:
//! - Message dispatch is on the hot path — every action goes through the bus
//! - RwLock allows concurrent reads with exclusive writes
//! - Atomic operations for counters and CAS without GIL
//! - Pre-allocated ring buffer avoids allocation on the fast path

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::{Arc, Mutex, RwLock};

// ─── Shared Memory Bus ────────────────────────────────────────

/// High-speed pub/sub message bus for inter-agent communication.
///
/// Messages are stored as Python objects. The bus uses per-mailbox
/// locking to avoid global contention.
#[pyclass(name = "SharedMemoryBus")]
pub struct SharedMemoryBus {
    /// topic -> set of subscriber_ids
    subscriptions: Arc<RwLock<HashMap<String, HashSet<String>>>>,
    /// subscriber_id -> mailbox (Vec of PyObject messages)
    mailboxes: Arc<RwLock<HashMap<String, Mutex<Vec<PyObject>>>>>,
    /// Metrics counters
    total_published: Arc<Mutex<u64>>,
    total_received: Arc<Mutex<u64>>,
    max_buffer_size: usize,
    max_mailbox_size: usize,
}

#[pymethods]
impl SharedMemoryBus {
    #[new]
    #[pyo3(signature = (max_buffer_size, max_mailbox_size))]
    fn new(max_buffer_size: Option<usize>, max_mailbox_size: Option<usize>) -> Self {
        SharedMemoryBus {
            subscriptions: Arc::new(RwLock::new(HashMap::new())),
            mailboxes: Arc::new(RwLock::new(HashMap::new())),
            total_published: Arc::new(Mutex::new(0)),
            total_received: Arc::new(Mutex::new(0)),
            max_buffer_size: max_buffer_size.unwrap_or(1000),
            max_mailbox_size: max_mailbox_size.unwrap_or(100),
        }
    }

    /// Publish a message to all subscribers of a topic.
    ///
    /// Returns True if the message was delivered to at least one subscriber.
    fn publish(&self, topic: &str, message: &Bound<'_, PyDict>) -> PyResult<bool> {
        let py = message.py();
        let msg_obj: PyObject = message.clone().into();

        let subs = self.subscriptions.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let subscribers = match subs.get(topic) {
            Some(s) => s.clone(),
            None => return Ok(false),
        };
        drop(subs); // release read lock

        let boxes = self.mailboxes.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let mut delivered = 0u32;
        for sub_id in &subscribers {
            if let Some(mailbox) = boxes.get(sub_id) {
                let mut mb = mailbox.lock().map_err(|e| {
                    PyRuntimeError::new_err(format!("Mailbox lock poisoned: {}", e))
                })?;
                if mb.len() < self.max_mailbox_size {
                    mb.push(msg_obj.clone_ref(py));
                    delivered += 1;
                }
            }
        }

        if delivered > 0 {
            let mut count = self.total_published.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Counter lock poisoned: {}", e))
            })?;
            *count += delivered as u64;
        }

        Ok(delivered > 0)
    }

    /// Subscribe a subscriber to a topic.
    fn subscribe(&self, topic: &str, subscriber_id: &str) -> PyResult<bool> {
        {
            let mut subs = self.subscriptions.write().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            subs.entry(topic.to_string())
                .or_insert_with(HashSet::new)
                .insert(subscriber_id.to_string());
        }

        // Ensure mailbox exists
        let mut boxes = self.mailboxes.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        boxes.entry(subscriber_id.to_string())
            .or_insert_with(|| Mutex::new(Vec::new()));

        Ok(true)
    }

    /// Unsubscribe a subscriber from a topic.
    fn unsubscribe(&self, topic: &str, subscriber_id: &str) -> PyResult<bool> {
        let mut subs = self.subscriptions.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        if let Some(sub_set) = subs.get_mut(topic) {
            Ok(sub_set.remove(subscriber_id))
        } else {
            Ok(false)
        }
    }

    /// Receive all pending messages for a subscriber.
    fn receive(&self, _py: Python<'_>, subscriber_id: &str) -> PyResult<Vec<PyObject>> {
        let boxes = self.mailboxes.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        if let Some(mailbox) = boxes.get(subscriber_id) {
            let mut mb = mailbox.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Mailbox lock poisoned: {}", e))
            })?;
            let messages: Vec<PyObject> = mb.drain(..).collect();

            if !messages.is_empty() {
                let mut count = self.total_received.lock().map_err(|e| {
                    PyRuntimeError::new_err(format!("Counter lock poisoned: {}", e))
                })?;
                *count += messages.len() as u64;
            }

            Ok(messages)
        } else {
            Ok(Vec::new())
        }
    }

    /// Broadcast a message to all subscribers of all topics.
    fn broadcast(&self, message: &Bound<'_, PyDict>) -> PyResult<usize> {
        let py = message.py();
        let msg_obj: PyObject = message.clone().into();

        let subs = self.subscriptions.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let all_subscribers: HashSet<String> = subs.values().flat_map(|s| s.iter().cloned()).collect();
        drop(subs);

        let boxes = self.mailboxes.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let mut delivered = 0usize;
        for sub_id in &all_subscribers {
            if let Some(mailbox) = boxes.get(sub_id) {
                let mut mb = mailbox.lock().map_err(|e| {
                    PyRuntimeError::new_err(format!("Mailbox lock poisoned: {}", e))
                })?;
                if mb.len() < self.max_mailbox_size {
                    mb.push(msg_obj.clone_ref(py));
                    delivered += 1;
                }
            }
        }

        if delivered > 0 {
            let mut count = self.total_published.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Counter lock poisoned: {}", e))
            })?;
            *count += delivered as u64;
        }

        Ok(delivered)
    }

    /// Get all active topics.
    fn get_topics(&self) -> PyResult<Vec<String>> {
        let subs = self.subscriptions.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(subs.keys().cloned().collect())
    }

    /// Get subscribers of a topic.
    fn get_subscribers(&self, topic: &str) -> PyResult<Vec<String>> {
        let subs = self.subscriptions.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        Ok(subs.get(topic).map(|s| s.iter().cloned().collect()).unwrap_or_default())
    }

    /// Check if a subscriber has pending messages.
    fn has_messages(&self, subscriber_id: &str) -> PyResult<bool> {
        let boxes = self.mailboxes.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        if let Some(mailbox) = boxes.get(subscriber_id) {
            let mb = mailbox.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Mailbox lock poisoned: {}", e))
            })?;
            Ok(!mb.is_empty())
        } else {
            Ok(false)
        }
    }

    /// Clear pending messages for a subscriber. Returns count cleared.
    fn clear(&self, subscriber_id: &str) -> PyResult<usize> {
        let boxes = self.mailboxes.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        if let Some(mailbox) = boxes.get(subscriber_id) {
            let mut mb = mailbox.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Mailbox lock poisoned: {}", e))
            })?;
            let count = mb.len();
            mb.clear();
            Ok(count)
        } else {
            Ok(0)
        }
    }

    /// Clear all bus state.
    fn clear_all(&self) -> PyResult<()> {
        {
            let mut subs = self.subscriptions.write().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            subs.clear();
        }
        {
            let boxes = self.mailboxes.write().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            for (_, mailbox) in boxes.iter() {
                let mut mb = mailbox.lock().map_err(|e| {
                    PyRuntimeError::new_err(format!("Mailbox lock poisoned: {}", e))
                })?;
                mb.clear();
            }
        }
        Ok(())
    }

    /// Get bus statistics.
    fn stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let result = PyDict::new_bound(py);
        let subs = self.subscriptions.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let boxes = self.mailboxes.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let total_subscribers: usize = subs.values().map(|s| s.len()).sum();
        let total_pending: usize = boxes.values().map(|m| {
            m.lock().map(|mb| mb.len()).unwrap_or(0)
        }).sum();

        let published = *self.total_published.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Counter lock poisoned: {}", e))
        })?;
        let received = *self.total_received.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Counter lock poisoned: {}", e))
        })?;

        result.set_item("topics_count", subs.len())?;
        result.set_item("total_subscribers", total_subscribers)?;
        result.set_item("total_pending_messages", total_pending)?;
        result.set_item("total_published", published)?;
        result.set_item("total_received", received)?;

        Ok(result.unbind())
    }
}

// ─── Shared State ──────────────────────────────────────────────

/// Thread-safe shared key-value store with atomic operations.
///
/// Uses RwLock for concurrent reads with exclusive writes.
/// Supports atomic increment/decrement and compare-and-swap.
#[pyclass(name = "SharedState")]
pub struct SharedState {
    data: Arc<RwLock<HashMap<String, PyObject>>>,
}

#[pymethods]
impl SharedState {
    #[new]
    fn new() -> Self {
        SharedState {
            data: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Get a value by key.
    fn get(&self, py: Python<'_>, key: &str) -> Option<PyObject> {
        let data = self.data.read().ok()?;
        data.get(key).map(|v| v.clone_ref(py))
    }

    /// Set a value. Returns True if the key was new.
    fn set(&self, py: Python<'_>, key: &str, value: PyObject) -> PyResult<bool> {
        let mut data = self.data.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let is_new = !data.contains_key(key);
        data.insert(key.to_string(), value.clone_ref(py));
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
        let mut data = self.data.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let current: i64 = data.get(key)
            .and_then(|v| v.extract::<i64>(py).ok())
            .unwrap_or(0);
        let new_val = current + delta;
        data.insert(key.to_string(), new_val.to_object(py));
        Ok(new_val)
    }

    /// Atomic decrement. Returns the new value.
    fn decr(&self, py: Python<'_>, key: &str, delta: i64) -> PyResult<i64> {
        self.incr(py, key, -delta)
    }

    /// Get or set a default value. Returns the existing value if present.
    fn get_or_set(&self, py: Python<'_>, key: &str, default: PyObject) -> PyResult<PyObject> {
        let mut data = self.data.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        if data.contains_key(key) {
            Ok(data.get(key).unwrap().clone_ref(py))
        } else {
            data.insert(key.to_string(), default.clone_ref(py));
            Ok(default)
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
        let mut data = self.data.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        match data.get(key) {
            Some(current) => {
                // Simple equality check using Python's ==
                let is_equal = current.bind(py).eq(expected.bind(py))?;
                if is_equal {
                    data.insert(key.to_string(), new);
                    Ok(true)
                } else {
                    Ok(false)
                }
            }
            None => {
                // Key doesn't exist — treat as not equal
                Ok(false)
            }
        }
    }

    /// Return a snapshot of all key-value pairs.
    fn snapshot(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let data = self.data.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let result = PyDict::new_bound(py);
        for (k, v) in data.iter() {
            result.set_item(k, v.clone_ref(py))?;
        }
        Ok(result.unbind())
    }

    /// Clear all data.
    fn clear(&self) -> PyResult<()> {
        let mut data = self.data.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        data.clear();
        Ok(())
    }
}

// ─── Ring Buffer ───────────────────────────────────────────────

/// Fixed-size circular buffer for event streams.
///
/// Pre-allocated with a fixed capacity. When full, the oldest
/// item is overwritten on push. O(1) push and pop operations.
#[pyclass(name = "RingBuffer")]
pub struct RingBuffer {
    buffer: Arc<RwLock<VecDeque<PyObject>>>,
    capacity: usize,
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

// ─── Unit Tests ────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ring_buffer_basic() {
        // Basic test without Python objects — just structure
        let cap = 4;
        let rb = RingBuffer {
            buffer: Arc::new(RwLock::new(VecDeque::with_capacity(cap))),
            capacity: cap,
        };
        assert_eq!(rb.capacity, 4);
        assert!(rb.is_empty().unwrap());
        assert!(!rb.is_full().unwrap());
    }

    #[test]
    fn test_shared_state_concurrent() {
        // Structure test without Python objects
        let state = SharedState {
            data: Arc::new(RwLock::new(HashMap::new())),
        };
        assert!(state.keys().unwrap().is_empty());
        assert!(!state.has("test").unwrap());
    }

    #[test]
    fn test_bus_structure() {
        let bus = SharedMemoryBus {
            subscriptions: Arc::new(RwLock::new(HashMap::new())),
            mailboxes: Arc::new(RwLock::new(HashMap::new())),
            total_published: Arc::new(Mutex::new(0)),
            total_received: Arc::new(Mutex::new(0)),
            max_buffer_size: 1000,
            max_mailbox_size: 100,
        };
        assert!(bus.get_topics().unwrap().is_empty());
    }
}
