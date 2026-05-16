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

use crate::errors::MemoryError;
use crate::types::{LearningVerdict, MemoryApprovalRequest, SemanticMapping};

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
            "Cannot collect evidence for episode {}", episode_id
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
            "Cannot resolve consensus for episode {}", episode_id
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
    pub fn compensate(&mut self, episode_id: &str, reason: &str) {
        if let Some(ep) = self.episodes.iter_mut().find(|e| e.id == episode_id) {
            ep.phase = LifecyclePhase::Compensated;
            ep.error = Some(reason.to_string());
        }
    }

    /// Returns an episode by ID.
    pub fn get(&self, episode_id: &str) -> Option<&LifecycleEpisode> {
        self.episodes.iter().find(|e| e.id == episode_id)
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
