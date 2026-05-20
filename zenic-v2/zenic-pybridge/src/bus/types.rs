//! Shared tests for the bus module.

#[cfg(test)]
mod tests {
    use super::{RingBuffer, SharedMemoryBus, SharedState};
    use std::collections::{HashMap, HashSet, VecDeque};
    use std::sync::{Arc, Mutex, RwLock};

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
            bincode_data: Arc::new(RwLock::new(HashMap::new())),
        };
        assert!(state.keys().unwrap().is_empty());
        assert!(!state.has("test").unwrap());
    }

    #[test]
    fn test_bus_structure() {
        let bus = SharedMemoryBus {
            subscriptions: Arc::new(RwLock::new(HashMap::new())),
            mailboxes: Arc::new(RwLock::new(HashMap::new())),
            rkyv_mailboxes: Arc::new(RwLock::new(HashMap::new())),
            total_published: Arc::new(Mutex::new(0)),
            total_received: Arc::new(Mutex::new(0)),
            max_buffer_size: 1000,
            max_mailbox_size: 100,
        };
        assert!(bus.get_topics().unwrap().is_empty());
    }
}
