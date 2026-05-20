//! Learning Lifecycle — LifecycleOrchestrator construction + accessor methods.

use std::sync::{Arc, Mutex};

use crate::cache::MemoryCache;
use crate::errors::MemoryError;
use crate::graph::{AuditEntry, SemanticGraph};
use crate::hitl_bridge::HitlBridge;
use crate::merkle_seal::MerkleSeal;
use crate::subscription_gate::SubscriptionGate;
use crate::types::{SubscriptionTier};
use crate::yaml_renderer::YamlRenderer;

use super::manager::LifecycleManager;

// ---------------------------------------------------------------------------
// LifecycleOrchestrator
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
    pub(crate) graph: Arc<Mutex<SemanticGraph>>,
    /// The LRU memory cache (internally thread-safe).
    pub(crate) cache: Arc<MemoryCache>,
    /// The Merkle seal (requires Mutex for mutable seal operations).
    pub(crate) merkle: Arc<Mutex<MerkleSeal>>,
    /// The YAML renderer (stateless, only &self methods).
    pub(crate) renderer: Arc<YamlRenderer>,
    /// The HITL bridge (requires Mutex for mutable operations).
    pub(crate) hitl: Arc<Mutex<HitlBridge>>,
    /// The subscription gate (stateless, only &self methods).
    pub(crate) subscription: Arc<SubscriptionGate>,
    /// The lifecycle manager (internal episode tracking).
    pub(crate) lifecycle: Arc<Mutex<LifecycleManager>>,
}

impl LifecycleOrchestrator {
    /// Creates a new lifecycle orchestrator with all components.
    pub fn new(
        graph: Arc<Mutex<SemanticGraph>>,
        cache: Arc<MemoryCache>,
        merkle: Arc<Mutex<MerkleSeal>>,
        renderer: Arc<YamlRenderer>,
        hitl: Arc<Mutex<HitlBridge>>,
        subscription: Arc<SubscriptionGate>,
    ) -> Self {
        Self {
            graph,
            cache,
            merkle,
            renderer,
            hitl,
            subscription,
            lifecycle: Arc::new(Mutex::new(LifecycleManager::new())),
        }
    }

    /// Creates a new orchestrator with default components for the given tier.
    ///
    /// Uses an in-memory SQLite database and tier-appropriate cache size.
    pub fn new_for_tier(tier: SubscriptionTier) -> Result<Self, MemoryError> {
        let graph = SemanticGraph::new(":memory:")?;
        let cache = MemoryCache::new_for_tier(tier);

        Ok(Self {
            graph: Arc::new(Mutex::new(graph)),
            cache: Arc::new(cache),
            merkle: Arc::new(Mutex::new(MerkleSeal::new())),
            renderer: Arc::new(YamlRenderer::new()),
            hitl: Arc::new(Mutex::new(HitlBridge::new())),
            subscription: Arc::new(SubscriptionGate::new(tier)),
            lifecycle: Arc::new(Mutex::new(LifecycleManager::new())),
        })
    }

    /// Returns a reference to the subscription gate.
    pub fn subscription(&self) -> &SubscriptionGate {
        &self.subscription
    }

    /// Returns a reference to the YAML renderer.
    pub fn renderer(&self) -> &YamlRenderer {
        &self.renderer
    }

    /// Returns the Merkle seal (locked).
    pub fn merkle(&self) -> &Arc<Mutex<MerkleSeal>> {
        &self.merkle
    }

    /// Returns the HITL bridge (locked).
    pub fn hitl(&self) -> &Arc<Mutex<HitlBridge>> {
        &self.hitl
    }

    /// Returns the semantic graph (locked).
    pub fn graph(&self) -> &Arc<Mutex<SemanticGraph>> {
        &self.graph
    }

    /// Returns the memory cache.
    pub fn cache(&self) -> &MemoryCache {
        &self.cache
    }

    /// Returns the lifecycle manager (locked).
    pub fn lifecycle(&self) -> &Arc<Mutex<LifecycleManager>> {
        &self.lifecycle
    }

    /// Performs Saga compensation for a failed episode.
    ///
    /// Rolls back all actions in reverse order.
    pub fn compensate_episode(&self, episode_id: &str, reason: &str) -> Result<(), MemoryError> {
        let graph = self.graph.lock().map_err(|e| {
            MemoryError::Internal(format!("graph lock poisoned: {}", e))
        })?;
        let mut hitl = self.hitl.lock().map_err(|e| {
            MemoryError::Internal(format!("hitl lock poisoned: {}", e))
        })?;
        let mut lifecycle = self.lifecycle.lock().map_err(|e| {
            MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
        })?;
        lifecycle.compensate(episode_id, reason, &graph, &self.cache, &mut hitl)
    }

    /// Persists an episode to the learning_audit table.
    ///
    /// Writes the episode state as a JSON detail blob with action
    /// "episode_persist". Can be loaded later with `load_episode`.
    pub fn persist_episode(&self, episode_id: &str) -> Result<(), MemoryError> {
        let episode = {
            let lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.get(episode_id).cloned().ok_or_else(|| {
                MemoryError::Internal(format!("Episode {} not found", episode_id))
            })?
        };

        let mapping_id = episode
            .mapping
            .as_ref()
            .map(|m| m.mapping_id.clone())
            .unwrap_or_default();

        let details = format!(
            "{{\"episode_id\":\"{}\",\"phase\":\"{}\",\"human_validated\":{},\"merkle_hash\":{}}}",
            episode.id,
            episode.phase,
            episode.human_validated,
            episode
                .merkle_hash
                .as_ref()
                .map(|h| format!("\"{}\"", h))
                .unwrap_or_else(|| "null".to_string())
        );

        let graph = self.graph.lock().map_err(|e| {
            MemoryError::Internal(format!("graph lock poisoned: {}", e))
        })?;
        graph.audit_log(&mapping_id, "episode_persist", "lifecycle_orchestrator", &details)
    }

    /// Loads episode data from the learning_audit table.
    ///
    /// Returns the audit entries matching "episode_persist" for the given
    /// mapping_id. This is a simplified load — full episode reconstruction
    /// would require a dedicated episodes table.
    pub fn load_episode(
        &self,
        mapping_id: &str,
    ) -> Result<Vec<AuditEntry>, MemoryError> {
        let graph = self.graph.lock().map_err(|e| {
            MemoryError::Internal(format!("graph lock poisoned: {}", e))
        })?;
        graph.query_audit_log(mapping_id, "episode_persist")
    }
}
