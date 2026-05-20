//! Lifecycle manager — Saga-like tracking of learning episodes.

use crate::cache::MemoryCache;
use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::hitl_bridge::HitlBridge;
use crate::types::{LearningVerdict, MemoryApprovalRequest, SemanticMapping};

use super::types::{CompensationAction, LifecycleEpisode, LifecyclePhase};

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
