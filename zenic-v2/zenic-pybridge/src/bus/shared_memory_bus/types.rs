//! SharedMemoryBus struct definition and field types.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex, RwLock};

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
    pub(crate) subscriptions: Arc<RwLock<HashMap<String, HashSet<String>>>>,
    /// subscriber_id -> mailbox (Vec of PyObject messages)
    pub(crate) mailboxes: Arc<RwLock<HashMap<String, Mutex<Vec<PyObject>>>>>,
    /// subscriber_id -> rkyv raw-bytes mailbox (for zero-copy Rust↔Rust)
    pub(crate) rkyv_mailboxes: Arc<RwLock<HashMap<String, Mutex<Vec<Vec<u8>>>>>>,
    /// Metrics counters
    pub(crate) total_published: Arc<Mutex<u64>>,
    pub(crate) total_received: Arc<Mutex<u64>>,
    pub(crate) max_buffer_size: usize,
    pub(crate) max_mailbox_size: usize,
}

impl SharedMemoryBus {
    pub(crate) fn new_inner(max_buffer_size: Option<usize>, max_mailbox_size: Option<usize>) -> Self {
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
}
