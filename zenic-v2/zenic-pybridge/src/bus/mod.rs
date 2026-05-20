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

pub mod publisher;
pub mod routing;
pub mod subscriber;
pub mod types;

pub use publisher::SharedMemoryBus;
pub use routing::RingBuffer;
pub use subscriber::SharedState;
