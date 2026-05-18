//! SharedMemoryBus — High-speed pub/sub message bus for inter-agent communication.
//!
//! Messages are stored as Python objects. The bus uses per-mailbox
//! locking to avoid global contention.
//!
//! Phase 3: Added rkyv raw-bytes mailboxes for zero-copy Rust<->Rust
//! communication through the bus, avoiding Python serialization overhead.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex, RwLock};

/// High-speed pub/sub message bus for inter-agent communication.
///
/// Messages are stored as Python objects. The bus uses per-mailbox
/// locking to avoid global contention.
///
/// Phase 3: Added rkyv raw-bytes mailboxes for zero-copy Rust<->Rust
/// communication through the bus, avoiding Python serialization overhead.
#[pyclass(name = "SharedMemoryBus")]
pub struct SharedMemoryBus {
    /// topic -> set of subscriber_ids
    pub(crate) subscriptions: Arc<RwLock<HashMap<String, HashSet<String>>>>,
    /// subscriber_id -> mailbox (Vec of PyObject messages)
    pub(crate) mailboxes: Arc<RwLock<HashMap<String, Mutex<Vec<PyObject>>>>>,
    /// subscriber_id -> rkyv raw-bytes mailbox (for zero-copy Rust<->Rust)
    pub(crate) rkyv_mailboxes: Arc<RwLock<HashMap<String, Mutex<Vec<Vec<u8>>>>>>,
    /// Metrics counters
    pub(crate) total_published: Arc<Mutex<u64>>,
    pub(crate) total_received: Arc<Mutex<u64>>,
    pub(crate) max_buffer_size: usize,
    pub(crate) max_mailbox_size: usize,
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
    /// This method avoids Python serialization overhead for Rust<->Rust
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
    /// This method avoids Python serialization overhead for Rust<->Rust
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
