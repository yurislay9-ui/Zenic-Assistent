//! Core types for the learning lifecycle.
//!
//! Defines the data structures used across the lifecycle module:
//! phases, episodes, compensation actions, and outcomes.

use crate::cache::MemoryCache;
use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::hitl_bridge::HitlBridge;
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
    pub(super) fn execute(
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
