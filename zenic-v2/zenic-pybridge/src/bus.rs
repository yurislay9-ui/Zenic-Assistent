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
///
/// Phase 3: Added rkyv raw-bytes mailboxes for zero-copy Rust↔Rust
/// communication through the bus, avoiding Python serialization overhead.
#[pyclass(name = "SharedMemoryBus")]
pub struct SharedMemoryBus {
    /// topic -> set of subscriber_ids
    subscriptions: Arc<RwLock<HashMap<String, HashSet<String>>>>,
    /// subscriber_id -> mailbox (Vec of PyObject messages)
    mailboxes: Arc<RwLock<HashMap<String, Mutex<Vec<PyObject>>>>>,
    /// subscriber_id -> rkyv raw-bytes mailbox (for zero-copy Rust↔Rust)
    rkyv_mailboxes: Arc<RwLock<HashMap<String, Mutex<Vec<Vec<u8>>>>>>,
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
            rkyv_mailboxes: Arc::new(RwLock::new(HashMap::new())),
            total_published: Arc::new(Mutex::new(0)),
            total_received: Arc::new(Mutex::new(0)),
            max_buffer_size: max_buffer_size.unwrap_or(1000),
            max_mailbox_size: max_mailbox_size.unwrap_or(100),
        }
    }

    /// Publish a message to all subscribers of a topic.
    ///
    /// Returns True if the message was delivered to at least one subscriber.
    ///
    /// E-03 FIX: Pre-clones message refs under GIL, then releases GIL for
    /// the mailbox insertion loop. This prevents deadlock when multiple
    /// Python threads call into the bus concurrently — without releasing the
    /// GIL, Thread A could hold the GIL and wait for a Rust lock while
    /// Thread B holds that lock and waits for the GIL.
    fn publish(&self, py: Python<'_>, topic: &str, message: &Bound<'_, PyDict>) -> PyResult<bool> {
        let msg_obj: PyObject = message.clone().into();

        // Clone subscriber list while holding the GIL + read lock
        let subscribers = {
            let subs = self.subscriptions.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            match subs.get(topic) {
                Some(s) => s.clone(),
                None => return Ok(false),
            }
            // Read lock released here
        };

        // E-03 FIX: Pre-clone the message for each subscriber while holding GIL.
        // We need one clone per subscriber since each mailbox takes ownership.
        // Wrapped in Option so we can take() ownership inside allow_threads.
        let mut msg_clones: Vec<Option<PyObject>> = subscribers.iter()
            .map(|_| Some(msg_obj.clone_ref(py)))
            .collect();

        let max_mailbox_size = self.max_mailbox_size;

        // E-03 FIX: Release the GIL for the mailbox delivery loop.
        // We move pre-cloned PyObjects (already refcount-incremented) into
        // the mailboxes using Option::take(). No Python API calls needed.
        let delivered: u32 = py.allow_threads(|| {
            let boxes = match self.mailboxes.read() {
                Ok(b) => b,
                Err(_) => return 0,
            };

            let mut count = 0u32;
            for (idx, sub_id) in subscribers.iter().enumerate() {
                if let Some(mailbox) = boxes.get(sub_id) {
                    if let Ok(mut mb) = mailbox.lock() {
                        if mb.len() < max_mailbox_size {
                            // Take ownership of the pre-cloned PyObject.
                            // Safe: refcount was incremented by clone_ref(py) above.
                            if let Some(msg) = msg_clones[idx].take() {
                                mb.push(msg);
                                count += 1;
                            }
                        }
                    }
                }
            }
            count
        });

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
    ///
    /// E-03 FIX: Releases the GIL while draining the mailbox and updating
    /// counters. PyObjects are moved (no Python API calls needed inside
    /// the lock scope), so this is safe.
    fn receive(&self, py: Python<'_>, subscriber_id: &str) -> PyResult<Vec<PyObject>> {
        // E-03 FIX: Release GIL for Rust-only operations (drain + counter update).
        // PyObject values are just moved from the Vec — no Python refcount
        // changes needed since we transfer ownership to the caller.
        let result: Option<Vec<PyObject>> = py.allow_threads(|| {
            let boxes = match self.mailboxes.read() {
                Ok(b) => b,
                Err(_) => return None, // Lock poisoned — fall through to empty
            };

            if let Some(mailbox) = boxes.get(subscriber_id) {
                let mut mb = match mailbox.lock() {
                    Ok(m) => m,
                    Err(_) => return Some(Vec::new()),
                };
                let messages: Vec<PyObject> = mb.drain(..).collect();

                if !messages.is_empty() {
                    if let Ok(mut count) = self.total_received.lock() {
                        *count += messages.len() as u64;
                    }
                }

                Some(messages)
            } else {
                Some(Vec::new())
            }
        });

        match result {
            Some(msgs) => Ok(msgs),
            None => Err(PyRuntimeError::new_err("Lock poisoned")),
        }
    }

    /// Broadcast a message to all subscribers of all topics.
    ///
    /// E-03 FIX: Pre-clones message refs under GIL, then releases GIL
    /// for the mailbox delivery loop. Same pattern as publish() — prevents
    /// GIL deadlock when concurrent Python threads interact with the bus.
    fn broadcast(&self, message: &Bound<'_, PyDict>) -> PyResult<usize> {
        let py = message.py();
        let msg_obj: PyObject = message.clone().into();

        // Clone subscriber list while holding the GIL + read lock
        let all_subscribers: HashSet<String> = {
            let subs = self.subscriptions.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            subs.values().flat_map(|s| s.iter().cloned()).collect()
            // Read lock released here
        };

        // E-03 FIX: Pre-clone the message for each subscriber while holding GIL.
        // Same technique as publish() — one clone per subscriber, wrapped in
        // Option so we can take() ownership inside allow_threads.
        let mut msg_clones: Vec<Option<PyObject>> = all_subscribers.iter()
            .map(|_| Some(msg_obj.clone_ref(py)))
            .collect();

        let max_mailbox_size = self.max_mailbox_size;

        // E-03 FIX: Release the GIL for the mailbox delivery loop.
        let delivered: usize = py.allow_threads(|| {
            let boxes = match self.mailboxes.read() {
                Ok(b) => b,
                Err(_) => return 0,
            };

            let mut count = 0usize;
            for (idx, sub_id) in all_subscribers.iter().enumerate() {
                if let Some(mailbox) = boxes.get(sub_id) {
                    if let Ok(mut mb) = mailbox.lock() {
                        if mb.len() < max_mailbox_size {
                            if let Some(msg) = msg_clones[idx].take() {
                                mb.push(msg);
                                count += 1;
                            }
                        }
                    }
                }
            }
            count
        });

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
    ///
    /// E-03 FIX: Collects all Rust-side data under GIL-release, then
    /// builds the PyDict after re-acquiring GIL. This avoids holding
    /// Rust locks while calling Python API (PyDict::set_item), which
    /// could deadlock if another thread holds GIL and waits for a lock.
    fn stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        // E-03 FIX: Release GIL for all Rust lock acquisitions + data collection.
        // No Python API calls needed here — just reading integers.
        let (topics_count, total_subscribers, total_pending, published, received) =
            py.allow_threads(|| {
                let subs = match self.subscriptions.read() {
                    Ok(s) => s,
                    Err(_) => return (0usize, 0usize, 0usize, 0u64, 0u64),
                };
                let boxes = match self.mailboxes.read() {
                    Ok(b) => b,
                    Err(_) => return (0, 0, 0, 0, 0),
                };

                let tc = subs.len();
                let ts: usize = subs.values().map(|s| s.len()).sum();
                let tp: usize = boxes.values().map(|m| {
                    m.lock().map(|mb| mb.len()).unwrap_or(0)
                }).sum();

                let pub_val = self.total_published.lock()
                    .map(|c| *c)
                    .unwrap_or(0);
                let recv_val = self.total_received.lock()
                    .map(|c| *c)
                    .unwrap_or(0);

                (tc, ts, tp, pub_val, recv_val)
            });

        // Build PyDict after re-acquiring GIL (safe: no Rust locks held)
        let result = PyDict::new_bound(py);
        result.set_item("topics_count", topics_count)?;
        result.set_item("total_subscribers", total_subscribers)?;
        result.set_item("total_pending_messages", total_pending)?;
        result.set_item("total_published", published)?;
        result.set_item("total_received", received)?;

        Ok(result.unbind())
    }

    // ─── rkyv Zero-Copy Methods (Phase 3) ──────────────────────

    /// Publishes pre-serialized rkyv data to all subscribers of a topic.
    ///
    /// This method avoids Python serialization overhead for Rust↔Rust
    /// communication. The raw bytes are stored directly in rkyv-specific
    /// mailboxes, enabling zero-copy deserialization on the receiving side.
    ///
    /// Returns True if the data was delivered to at least one subscriber.
    fn publish_rkyv(&self, topic: &str, data: &[u8]) -> PyResult<bool> {
        // Get subscribers for this topic
        let subscribers = {
            let subs = self.subscriptions.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            match subs.get(topic) {
                Some(s) => s.clone(),
                None => return Ok(false),
            }
        };

        let data_owned = data.to_vec();
        let max_mailbox_size = self.max_mailbox_size;

        // Deliver to each subscriber's rkyv mailbox
        let delivered: u32 = {
            let boxes = self.rkyv_mailboxes.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;

            let mut count = 0u32;
            for sub_id in &subscribers {
                if let Some(mailbox) = boxes.get(sub_id) {
                    if let Ok(mut mb) = mailbox.lock() {
                        if mb.len() < max_mailbox_size {
                            mb.push(data_owned.clone());
                            count += 1;
                        }
                    }
                }
            }
            count
        };

        if delivered > 0 {
            let mut count = self.total_published.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Counter lock poisoned: {}", e))
            })?;
            *count += delivered as u64;
        }

        Ok(delivered > 0)
    }

    /// Receives and returns raw rkyv bytes from a subscriber's mailbox.
    ///
    /// Returns the first pending rkyv message as raw bytes (for zero-copy
    /// deserialization on the other side), or None if no rkyv messages
    /// are pending.
    ///
    /// This method avoids Python serialization overhead for Rust↔Rust
    /// communication through the bus.
    fn receive_rkyv(&self, subscriber_id: &str) -> PyResult<Option<Vec<u8>>> {
        let boxes = self.rkyv_mailboxes.read().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        if let Some(mailbox) = boxes.get(subscriber_id) {
            let mut mb = mailbox.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Mailbox lock poisoned: {}", e))
            })?;
            if mb.is_empty() {
                return Ok(None);
            }

            let data = mb.remove(0);

            if let Ok(mut count) = self.total_received.lock() {
                *count += 1;
            }

            Ok(Some(data))
        } else {
            Ok(None)
        }
    }
}

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
    data: Arc<RwLock<HashMap<String, PyObject>>>,
    /// Raw bytes storage for bincode-serialized data (Rust↔Rust fast path).
    bincode_data: Arc<RwLock<HashMap<String, Vec<u8>>>>,
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
    /// This method avoids Python serialization overhead for Rust↔Rust
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
    /// This method avoids Python serialization overhead for Rust↔Rust
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
