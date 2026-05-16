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
use crate::errors::MemoryError;
use crate::graph::{AuditEntry, SemanticGraph};
use crate::hitl_bridge::HitlBridge;
use crate::merkle_seal::MerkleSeal;
use crate::subscription_gate::SubscriptionGate;
use crate::types::{
    LearningMechanism, LearningVerdict, MemoryApprovalRequest, SemanticMapping, SubscriptionTier,
};
use crate::yaml_renderer::YamlRenderer;

// ---------------------------------------------------------------------------
// LifecyclePhase
// ---------------------------------------------------------------------------

/// The phase of a learning lifecycle episode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LifecyclePhase {
    /// A hypothesis has been proposed by the deterministic layer.
    Proposed,
    /// Evidence collected (Layer 2).
    EvidenceCollected,
    /// Consensus resolved (Layer 3).
    ConsensusResolved,
    /// The LLM has classified the hypothesis (SÍ/NO) (Layer 4).
    Classified,
    /// Human validation in progress (HITL).
    HumanValidation,
    /// Knowledge committed to semantic graph + Merkle sealed.
    Committed,
    /// Hot-reload into zenic-policy completed.
    Deployed,
    /// The episode was rejected and discarded.
    Discarded,
    /// Compensation applied (Saga rollback).
    Compensated,
}

impl std::fmt::Display for LifecyclePhase {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Proposed => write!(f, "proposed"),
            Self::EvidenceCollected => write!(f, "evidence_collected"),
            Self::ConsensusResolved => write!(f, "consensus_resolved"),
            Self::Classified => write!(f, "classified"),
            Self::HumanValidation => write!(f, "human_validation"),
            Self::Committed => write!(f, "committed"),
            Self::Deployed => write!(f, "deployed"),
            Self::Discarded => write!(f, "discarded"),
            Self::Compensated => write!(f, "compensated"),
        }
    }
}

// ---------------------------------------------------------------------------
// LifecycleEpisode
// ---------------------------------------------------------------------------

/// A single learning lifecycle episode.
#[derive(Debug, Clone)]
pub struct LifecycleEpisode {
    /// Unique identifier for this episode.
    pub id: String,
    /// The current phase.
    pub phase: LifecyclePhase,
    /// The semantic mapping being learned.
    pub mapping: Option<SemanticMapping>,
    /// The LLM verdict (if classified).
    pub verdict: Option<LearningVerdict>,
    /// The HITL approval request (if submitted).
    pub approval_request: Option<MemoryApprovalRequest>,
    /// Whether human validation has been completed.
    pub human_validated: bool,
    /// Merkle hash after sealing.
    pub merkle_hash: Option<String>,
    /// Error message if the episode failed.
    pub error: Option<String>,
    /// Compensation actions accumulated during the episode.
    pub compensation_stack: Vec<CompensationAction>,
}

// ---------------------------------------------------------------------------
// CompensationAction
// ---------------------------------------------------------------------------

/// A compensating action in the Saga pattern.
///
/// Each step in the learning lifecycle can record a compensation
/// action that reverses its effect if a later step fails.
#[derive(Debug, Clone)]
pub enum CompensationAction {
    /// Remove a mapping from the semantic graph.
    RemoveFromGraph {
        /// The mapping ID to remove.
        mapping_id: String,
    },
    /// Evict an entry from the memory cache.
    EvictFromCache {
        /// The origin key to evict.
        origin: String,
        /// The tenant that owns the entry.
        tenant_id: String,
    },
    /// Unseal a Merkle hash (mark as unverified).
    UnsealMerkle {
        /// The mapping ID to unseal.
        mapping_id: String,
    },
    /// Revoke a HITL approval.
    RevokeHITLApproval {
        /// The mapping ID whose approval to revoke.
        mapping_id: String,
    },
    /// Revert a policy YAML deployment.
    RevertPolicyYaml {
        /// The mapping ID whose YAML to revert.
        mapping_id: String,
    },
}

impl CompensationAction {
    /// Returns a human-readable description of this compensation action.
    pub fn description(&self) -> String {
        match self {
            Self::RemoveFromGraph { mapping_id } => {
                format!("Remove mapping {} from graph", mapping_id)
            }
            Self::EvictFromCache { origin, tenant_id } => {
                format!("Evict '{}' from cache for tenant '{}'", origin, tenant_id)
            }
            Self::UnsealMerkle { mapping_id } => {
                format!("Unseal Merkle hash for mapping {}", mapping_id)
            }
            Self::RevokeHITLApproval { mapping_id } => {
                format!("Revoke HITL approval for mapping {}", mapping_id)
            }
            Self::RevertPolicyYaml { mapping_id } => {
                format!("Revert policy YAML for mapping {}", mapping_id)
            }
        }
    }

    /// Executes this compensation action against the orchestrator components.
    fn execute(
        &self,
        graph: &SemanticGraph,
        cache: &MemoryCache,
        hitl: &mut HitlBridge,
    ) -> Result<(), MemoryError> {
        match self {
            Self::RemoveFromGraph { mapping_id } => {
                let _ = graph.delete_mapping(mapping_id);
                Ok(())
            }
            Self::EvictFromCache { origin, tenant_id } => {
                cache.remove(origin, tenant_id);
                Ok(())
            }
            Self::RevokeHITLApproval { mapping_id } => {
                // Mark as expired in HITL bridge
                let _ = hitl.expire(mapping_id);
                Ok(())
            }
            // UnsealMerkle and RevertPolicyYaml are no-ops for now
            // (Merkle doesn't support unseal, and YAML is a file that
            // would need external coordination to revert)
            Self::UnsealMerkle { .. } => Ok(()),
            Self::RevertPolicyYaml { .. } => Ok(()),
        }
    }
}

// ---------------------------------------------------------------------------
// LifecycleManager
// ---------------------------------------------------------------------------

/// Manager for the learning lifecycle.
///
/// Implements a Saga-like pattern for learning episodes:
/// each step can be compensated (rolled back) if a later step fails.
pub struct LifecycleManager {
    /// Active episodes.
    episodes: Vec<LifecycleEpisode>,
}

impl LifecycleManager {
    /// Creates a new lifecycle manager.
    pub fn new() -> Self {
        Self {
            episodes: Vec::new(),
        }
    }

    /// Starts a new learning episode from a proposed mapping.
    pub fn start_episode(&mut self, mapping: SemanticMapping) -> &LifecycleEpisode {
        let episode = LifecycleEpisode {
            id: uuid::Uuid::new_v4().to_string(),
            phase: LifecyclePhase::Proposed,
            mapping: Some(mapping),
            verdict: None,
            approval_request: None,
            human_validated: false,
            merkle_hash: None,
            error: None,
            compensation_stack: Vec::new(),
        };
        self.episodes.push(episode);
        self.episodes.last().unwrap()
    }

    /// Advances an episode to the evidence-collected phase.
    pub fn collect_evidence(&mut self, episode_id: &str) -> Result<(), MemoryError> {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            if ep.phase == LifecyclePhase::Proposed {
                ep.phase = LifecyclePhase::EvidenceCollected;
                return Ok(());
            }
        }
        Err(MemoryError::HypothesisFailed(format!(
            "Cannot collect evidence for episode {}",
            episode_id
        )))
    }

    /// Advances an episode to the consensus-resolved phase.
    pub fn resolve_consensus(&mut self, episode_id: &str) -> Result<(), MemoryError> {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            if ep.phase == LifecyclePhase::EvidenceCollected {
                ep.phase = LifecyclePhase::ConsensusResolved;
                return Ok(());
            }
        }
        Err(MemoryError::HypothesisFailed(format!(
            "Cannot resolve consensus for episode {}",
            episode_id
        )))
    }

    /// Classifies an episode with an LLM verdict.
    pub fn classify(&mut self, episode_id: &str, verdict: LearningVerdict) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.phase = LifecyclePhase::Classified;
            ep.verdict = Some(verdict);
        }
    }

    /// Submits an episode for HITL validation.
    pub fn submit_for_hitl(&mut self, episode_id: &str, request: MemoryApprovalRequest) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.phase = LifecyclePhase::HumanValidation;
            ep.approval_request = Some(request);
        }
    }

    /// Validates an episode after HITL approval.
    pub fn validate(&mut self, episode_id: &str) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.phase = LifecyclePhase::Committed;
            ep.human_validated = true;
        }
    }

    /// Seals an episode with a Merkle hash.
    pub fn seal(&mut self, episode_id: &str, merkle_hash: String) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.merkle_hash = Some(merkle_hash);
        }
    }

    /// Deploys an episode (hot-reload into zenic-policy).
    pub fn deploy(&mut self, episode_id: &str) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.phase = LifecyclePhase::Deployed;
        }
    }

    /// Discards an episode (rejected by IA or HITL).
    pub fn discard(&mut self, episode_id: &str, reason: &str) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.phase = LifecyclePhase::Discarded;
            ep.error = Some(reason.to_string());
        }
    }

    /// Compensates (rolls back) an episode (Saga pattern).
    ///
    /// Executes all accumulated compensation actions in reverse order.
    pub fn compensate(
        &mut self,
        episode_id: &str,
        reason: &str,
        graph: &SemanticGraph,
        cache: &MemoryCache,
        hitl: &mut HitlBridge,
    ) -> Result<(), MemoryError> {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.error = Some(reason.to_string());

            // Execute compensation actions in reverse order (LIFO)
            let actions: Vec<CompensationAction> =
                ep.compensation_stack.drain(..).rev().collect();
            for action in actions {
                action.execute(graph, cache, hitl)?;
            }

            ep.phase = LifecyclePhase::Compensated;
            Ok(())
        } else {
            Err(MemoryError::Internal(format!(
                "Episode {} not found for compensation",
                episode_id
            )))
        }
    }

    /// Simple compensation that marks the episode as compensated without
    /// executing compensation actions. Used by PyO3 bridge where graph/
    /// cache/hitl references are not directly available.
    pub fn compensate_simple(&mut self, episode_id: &str, reason: &str) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.phase = LifecyclePhase::Compensated;
            ep.error = Some(reason.to_string());
            ep.compensation_stack.clear();
        }
    }

    /// Returns an episode by ID.
    pub fn get(&self, episode_id: &str) -> Option<&LifecycleEpisode> {
        self.episodes.iter().find(|e| e.id == episode_id)
    }

    /// Returns a mutable reference to an episode by ID.
    pub fn get_mut(&mut self, episode_id: &str) -> Option<&mut LifecycleEpisode> {
        self.episodes.iter_mut().find(|e| e.id == episode_id)
    }

    /// Returns the number of active episodes.
    pub fn len(&self) -> usize {
        self.episodes.len()
    }

    /// Returns `true` if there are no active episodes.
    pub fn is_empty(&self) -> bool {
        self.episodes.is_empty()
    }

    /// Returns episodes filtered by phase.
    pub fn by_phase(&self, phase: LifecyclePhase) -> Vec<&LifecycleEpisode> {
        self.episodes.iter().filter(|e| e.phase == phase).collect()
    }
}

impl Default for LifecycleManager {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// EpisodeOutcome
// ---------------------------------------------------------------------------

/// The outcome of running a learning episode through the orchestrator.
#[derive(Debug, Clone)]
pub enum EpisodeOutcome {
    /// Full cycle completed (deterministic Layer 1 resolution or auto-approved).
    Completed(EpisodeResult),
    /// HITL approval is pending (requires human input to continue).
    PendingHITL {
        /// The episode ID for later completion.
        episode_id: String,
        /// The mapping awaiting approval.
        mapping: SemanticMapping,
        /// The approval request to be reviewed.
        approval_request: MemoryApprovalRequest,
    },
    /// Episode was rejected by IA verdict.
    Rejected {
        /// The episode ID.
        episode_id: String,
        /// The reason for rejection.
        reason: String,
    },
}

// ---------------------------------------------------------------------------
// EpisodeResult
// ---------------------------------------------------------------------------

/// Result of a completed learning episode.
#[derive(Debug, Clone)]
pub struct EpisodeResult {
    /// The episode identifier.
    pub episode_id: String,
    /// The approved mapping.
    pub mapping: SemanticMapping,
    /// The final phase reached.
    pub phase: LifecyclePhase,
    /// The Merkle hash seal (if sealed).
    pub merkle_hash: Option<String>,
    /// The rendered YAML (if deployed).
    pub yaml: Option<String>,
}

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
    graph: Arc<Mutex<SemanticGraph>>,
    /// The LRU memory cache (internally thread-safe).
    cache: Arc<MemoryCache>,
    /// The Merkle seal (requires Mutex for mutable seal operations).
    merkle: Arc<Mutex<MerkleSeal>>,
    /// The YAML renderer (stateless, only &self methods).
    renderer: Arc<YamlRenderer>,
    /// The HITL bridge (requires Mutex for mutable operations).
    hitl: Arc<Mutex<HitlBridge>>,
    /// The subscription gate (stateless, only &self methods).
    subscription: Arc<SubscriptionGate>,
    /// The lifecycle manager (internal episode tracking).
    lifecycle: Arc<Mutex<LifecycleManager>>,
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

    /// Runs the full learning cycle for a proposed mapping.
    ///
    /// Steps:
    /// 1. Check subscription gate
    /// 2. Start episode
    /// 3. Generate hypothesis (if needed)
    /// 4. Collect evidence
    /// 5. Resolve consensus
    /// 6. Classify (IA binary verdict if needed)
    /// 7. Submit for HITL
    /// 8. Validate HITL approval
    /// 9. Seal with Merkle
    /// 10. Render YAML for hot-reload
    /// 11. Deploy to cache
    ///
    /// If the verdict requires HITL, returns `EpisodeOutcome::PendingHITL`.
    /// If the verdict is deterministic (Layer 1), completes the full cycle.
    /// If the IA rejects, returns `EpisodeOutcome::Rejected`.
    pub fn run_episode(
        &self,
        origin: &str,
        relation: &str,
        destination: &str,
        mechanism: LearningMechanism,
        tenant_id: &str,
    ) -> Result<EpisodeOutcome, MemoryError> {
        // Step 1: Check subscription gate
        self.subscription.check_mechanism(mechanism)?;

        // Check mapping quota
        let mapping_count = {
            let graph = self.graph.lock().map_err(|e| {
                MemoryError::Internal(format!("graph lock poisoned: {}", e))
            })?;
            graph.count_mappings(tenant_id)?
        };
        self.subscription.check_mapping_quota(mapping_count)?;

        // Step 2: Start episode with a new mapping
        let mapping = SemanticMapping::new(
            uuid::Uuid::new_v4().to_string(),
            origin.to_string(),
            relation.to_string(),
            destination.to_string(),
            mechanism,
        );
        let mut mapping = mapping;
        mapping.tenant_id = tenant_id.to_string();

        let episode_id = {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            let ep = lifecycle.start_episode(mapping.clone());
            ep.id.clone()
        };

        // Insert into graph and record compensation
        {
            let graph = self.graph.lock().map_err(|e| {
                MemoryError::Internal(format!("graph lock poisoned: {}", e))
            })?;
            graph.insert_mapping(&mapping)?;
        }
        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            if let Some(ep) = lifecycle.get_mut(&episode_id) {
                ep.compensation_stack.push(CompensationAction::RemoveFromGraph {
                    mapping_id: mapping.mapping_id.clone(),
                });
            }
        }

        // Step 3-4: Collect evidence (simplified — mark as collected)
        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.collect_evidence(&episode_id)?;
        }

        // Step 5: Resolve consensus (simplified — mark as resolved)
        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.resolve_consensus(&episode_id)?;
        }

        // Step 6: Classify — determine if IA is needed
        // For now, we simulate the verdict:
        // - OntologyBase → deterministic accept (Layer 1)
        // - SchemaDrift with high confidence → deterministic
        // - Others → need HITL
        let verdict = if mechanism == LearningMechanism::OntologyBase {
            LearningVerdict::deterministic_accept(mapping.clone())
        } else {
            // Simulate an IA verdict (in production, this would call the LLM)
            LearningVerdict::ia_verdict(
                mapping.clone(),
                true, // IA says YES
                vec![format!("Detected {} pattern", mechanism)],
                vec![],
                0.75,
            )
        };

        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.classify(&episode_id, verdict.clone());
        }

        // If IA rejected, discard
        if !verdict.ia_response && !verdict.is_deterministic() {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.discard(&episode_id, "IA verdict: NO");
            return Ok(EpisodeOutcome::Rejected {
                episode_id,
                reason: "IA verdict: NO".to_string(),
            });
        }

        // Step 7: Submit for HITL (if not deterministic Layer 1)
        if verdict.is_deterministic() {
            // Layer 1 resolved — skip HITL, go straight to commit
            let result = self.complete_episode_internal(&episode_id, &mapping, tenant_id, None)?;
            return Ok(EpisodeOutcome::Completed(result));
        }

        // Needs HITL — create approval request and submit
        let approval_request = MemoryApprovalRequest::from_verdict(
            &verdict,
            String::new(), // Will be filled by admin
        );

        {
            let mut hitl = self.hitl.lock().map_err(|e| {
                MemoryError::Internal(format!("hitl lock poisoned: {}", e))
            })?;
            hitl.submit_for_review(approval_request.clone())?;
        }

        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.submit_for_hitl(&episode_id, approval_request.clone());
        }

        Ok(EpisodeOutcome::PendingHITL {
            episode_id,
            mapping,
            approval_request,
        })
    }

    /// Completes a learning episode after HITL approval.
    ///
    /// Steps 8-11: validate HITL, seal Merkle, render YAML, deploy cache.
    pub fn complete_episode_after_hitl(
        &self,
        episode_id: &str,
        admin_evidence_review: bool,
        admin_justification: String,
        risk_acknowledgment: bool,
        admin_session_id: String,
    ) -> Result<EpisodeResult, MemoryError> {
        // Step 8: Approve via HITL
        let (mapping, approval) = {
            let mut hitl = self.hitl.lock().map_err(|e| {
                MemoryError::Internal(format!("hitl lock poisoned: {}", e))
            })?;

            // Find the mapping_id from the lifecycle
            let mapping_id = {
                let lifecycle = self.lifecycle.lock().map_err(|e| {
                    MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
                })?;
                let ep = lifecycle.get(episode_id).ok_or_else(|| {
                    MemoryError::Internal(format!("Episode {} not found", episode_id))
                })?;
                ep.mapping
                    .as_ref()
                    .map(|m| m.mapping_id.clone())
                    .unwrap_or_default()
            };

            let outcome = hitl.approve(
                &mapping_id,
                admin_evidence_review,
                admin_justification,
                risk_acknowledgment,
                admin_session_id,
            )?;

            if outcome != crate::hitl_bridge::HitlOutcome::Approved {
                return Err(MemoryError::ApprovalRequired(
                    "HITL approval was not granted".to_string(),
                ));
            }

            // Get the approved request back
            let approval = hitl
                .find_completed(&mapping_id)
                .cloned()
                .ok_or_else(|| {
                    MemoryError::Internal("Approved request not found in completed queue".to_string())
                })?;

            let mapping = {
                let lifecycle = self.lifecycle.lock().map_err(|e| {
                    MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
                })?;
                let ep = lifecycle.get(episode_id).ok_or_else(|| {
                    MemoryError::Internal(format!("Episode {} not found", episode_id))
                })?;
                ep.mapping.clone().ok_or_else(|| {
                    MemoryError::Internal("Episode has no mapping".to_string())
                })?
            };

            (mapping, approval)
        };

        // Validate the episode
        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.validate(episode_id);
        }

        self.complete_episode_internal(episode_id, &mapping, &mapping.tenant_id, Some(&approval))
    }

    /// Internal: completes steps 9-11 (seal, render, deploy).
    fn complete_episode_internal(
        &self,
        episode_id: &str,
        mapping: &SemanticMapping,
        tenant_id: &str,
        approval: Option<&MemoryApprovalRequest>,
    ) -> Result<EpisodeResult, MemoryError> {
        // Step 9: Seal with Merkle
        let merkle_hash = {
            let mut merkle = self.merkle.lock().map_err(|e| {
                MemoryError::Internal(format!("merkle lock poisoned: {}", e))
            })?;
            merkle.seal_mapping(mapping)?
        };

        // Update mapping with merkle hash and approved status
        let mut sealed_mapping = mapping.clone();
        sealed_mapping.merkle_hash = Some(merkle_hash.clone());
        sealed_mapping.approved = true;

        // Update in graph
        {
            let graph = self.graph.lock().map_err(|e| {
                MemoryError::Internal(format!("graph lock poisoned: {}", e))
            })?;
            graph.approve_mapping(&mapping.mapping_id, &merkle_hash)?;
        }

        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.seal(episode_id, merkle_hash.clone());
            if let Some(ep) = lifecycle.get_mut(episode_id) {
                ep.mapping = Some(sealed_mapping.clone());
                ep.compensation_stack.push(CompensationAction::UnsealMerkle {
                    mapping_id: mapping.mapping_id.clone(),
                });
            }
        }

        // Step 10: Render YAML for hot-reload
        let yaml = if let Some(appr) = approval {
            self.renderer.render_for_hot_reload(&sealed_mapping, appr)?
        } else {
            // No HITL approval (deterministic Layer 1) — create a synthetic
            // approval for rendering
            let synthetic_approval = MemoryApprovalRequest {
                admin_evidence_review: true,
                admin_justification: "Automatically approved by deterministic Layer 1 resolution — no IA activation required".to_string(),
                risk_acknowledgment: true,
                admin_session_id: "deterministic_layer_1_auto_approved_00000000".to_string(),
                mapping_id: mapping.mapping_id.clone(),
                ia_question: mapping.binary_question(),
                ia_response: true,
                evidence_for: vec!["deterministic_match".to_string()],
                evidence_against: vec![],
                consensus_score: 1.0,
            };
            self.renderer
                .render_for_hot_reload(&sealed_mapping, &synthetic_approval)?
        };

        // Step 11: Deploy to cache
        self.cache.insert(
            &mapping.origin,
            &sealed_mapping,
            tenant_id,
        )?;
        {
            let mut lifecycle = self.lifecycle.lock().map_err(|e| {
                MemoryError::Internal(format!("lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.deploy(episode_id);
            if let Some(ep) = lifecycle.get_mut(episode_id) {
                ep.compensation_stack.push(CompensationAction::EvictFromCache {
                    origin: mapping.origin.clone(),
                    tenant_id: tenant_id.to_string(),
                });
            }
        }

        Ok(EpisodeResult {
            episode_id: episode_id.to_string(),
            mapping: sealed_mapping,
            phase: LifecyclePhase::Deployed,
            merkle_hash: Some(merkle_hash),
            yaml: Some(yaml),
        })
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
}


