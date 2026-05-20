//! Learning Lifecycle — Saga workflow for learning episodes [T1+T2]
//!
//! Manages the full lifecycle of a memory learning episode from
//! hypothesis to validated knowledge. Uses Saga pattern for reliability.
//!
//! Flow:
//! 1. Deterministic Layer proposes hypothesis
//! 2. IA classifies SÍ/NO (Layer 4 only if needed)
//! 3. HITL validates with 3 mandatory fields
//! 4. MerkleLedger seals with BLAKE3
//! 5. YAML rendered for hot-reload
//! 6. Cache LRU updated
//! 7. Next time: Layer 1 resolves in <5ms, IA not activated
//!
//! Phase 4 enhancements:
//! - LifecycleOrchestrator: full integration of all Memory Chip components
//! - CompensationAction: Saga compensation tracking
//! - Episode persistence: write/load to learning_audit table
//! - Automatic phase transitions with component calls

use std::sync::{Arc, Mutex};

use crate::cache::MemoryCache;
use crate::graph::SemanticGraph;
use crate::hitl_bridge::HitlBridge;
use crate::merkle_seal::MerkleSeal;
use crate::subscription_gate::SubscriptionGate;
use crate::yaml_renderer::YamlRenderer;

// ---------------------------------------------------------------------------
// Submodules
// ---------------------------------------------------------------------------

pub mod manager;
pub mod persistence;
pub mod transitions;
pub mod types;

// ---------------------------------------------------------------------------
// LifecycleOrchestrator (struct definition)
// ---------------------------------------------------------------------------

/// Full lifecycle orchestrator that integrates all Memory Chip components.
///
/// Coordinates the complete learning cycle from hypothesis to deployment,
/// calling the appropriate component methods at each phase transition.
///
/// # Components
///
/// - `SemanticGraph` — persistent storage for mappings
/// - `MemoryCache` — hot-path LRU cache
/// - `MerkleSeal` — cryptographic integrity verification
/// - `YamlRenderer` — YAML rendering for policy hot-reload
/// - `HitlBridge` — human-in-the-loop approval
/// - `SubscriptionGate` — feature gating by subscription tier
pub struct LifecycleOrchestrator {
    /// The semantic graph (SQLite-backed, requires Mutex for Sync).
    pub(super) graph: Arc<Mutex<SemanticGraph>>,
    /// The LRU memory cache (internally thread-safe).
    pub(super) cache: Arc<MemoryCache>,
    /// The Merkle seal (requires Mutex for mutable seal operations).
    pub(super) merkle: Arc<Mutex<MerkleSeal>>,
    /// The YAML renderer (stateless, only &self methods).
    pub(super) renderer: Arc<YamlRenderer>,
    /// The HITL bridge (requires Mutex for mutable operations).
    pub(super) hitl: Arc<Mutex<HitlBridge>>,
    /// The subscription gate (stateless, only &self methods).
    pub(super) subscription: Arc<SubscriptionGate>,
    /// The lifecycle manager (internal episode tracking).
    pub(super) lifecycle: Arc<Mutex<LifecycleManager>>,
}

// ---------------------------------------------------------------------------
// Re-exports — every public symbol accessible from `crate::lifecycle::*`
// ---------------------------------------------------------------------------

pub use types::{
    CompensationAction, EpisodeOutcome, EpisodeResult, LifecycleEpisode, LifecyclePhase,
};

pub use manager::LifecycleManager;
