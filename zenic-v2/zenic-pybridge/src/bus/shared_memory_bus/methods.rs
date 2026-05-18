//! Core PyO3 methods for SharedMemoryBus: pub/sub, broadcast, queries.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::types::SharedMemoryBus;

#[pymethods]
impl SharedMemoryBus {
    #[new]
    #[pyo3(signature = (max_buffer_size, max_mailbox_size))]
    fn new(max_buffer_size: Option<usize>, max_mailbox_size: Option<usize>) -> Self {
        SharedMemoryBus::new_inner(max_buffer_size, max_mailbox_size)
    }

    /// Publish a message to all subscribers of a topic.
    fn publish(&self, py: Python<'_>, topic: &str, message: &Bound<'_, PyDict>) -> PyResult<bool> {
        let msg_obj: PyObject = message.clone().into();

        let subscribers = {
            let subs = self.subscriptions.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            match subs.get(topic) {
                Some(s) => s.clone(),
                None => return Ok(false),
            }
        };

        let mut msg_clones: Vec<Option<PyObject>> = subscribers.iter()
            .map(|_| Some(msg_obj.clone_ref(py)))
            .collect();

        let max_mailbox_size = self.max_mailbox_size;

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

        let mut boxes = self.mailboxes.write().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        boxes.entry(subscriber_id.to_string())
            .or_insert_with(|| std::sync::Mutex::new(Vec::new()));

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
    fn receive(&self, py: Python<'_>, subscriber_id: &str) -> PyResult<Vec<PyObject>> {
        let result: Option<Vec<PyObject>> = py.allow_threads(|| {
            let boxes = match self.mailboxes.read() {
                Ok(b) => b,
                Err(_) => return None,
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
    fn broadcast(&self, message: &Bound<'_, PyDict>) -> PyResult<usize> {
        let py = message.py();
        let msg_obj: PyObject = message.clone().into();

        let all_subscribers: std::collections::HashSet<String> = {
            let subs = self.subscriptions.read().map_err(|e| {
                PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
            })?;
            subs.values().flat_map(|s| s.iter().cloned()).collect()
        };

        let mut msg_clones: Vec<Option<PyObject>> = all_subscribers.iter()
            .map(|_| Some(msg_obj.clone_ref(py)))
            .collect();

        let max_mailbox_size = self.max_mailbox_size;

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
    fn stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
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
    fn publish_rkyv(&self, topic: &str, data: &[u8]) -> PyResult<bool> {
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

// Need HashSet import for subscribe/unsubscribe
use std::collections::HashSet;
