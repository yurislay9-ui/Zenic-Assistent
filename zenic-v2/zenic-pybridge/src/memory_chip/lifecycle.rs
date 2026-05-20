//! Learning lifecycle operations for the Memory Chip.
//!
//! Contains helper functions for starting and advancing learning
//! lifecycle episodes — extracted from the MemoryChip PyO3 methods.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

use zenic_memory::{LifecyclePhase, SemanticMapping};

use super::types::{parse_lifecycle_phase, parse_mechanism, MemoryChipInner};

/// Starts a learning lifecycle episode.
///
/// Returns the episode_id.
pub(crate) fn start_episode(
    inner: &MemoryChipInner,
    origin: &str,
    relation: &str,
    destination: &str,
    mechanism: &str,
    tenant_id: &str,
) -> PyResult<String> {
    let mech = parse_mechanism(mechanism)?;
    let mapping_id = uuid::Uuid::new_v4().to_string();
    let mut mapping = SemanticMapping::new(
        mapping_id,
        origin.to_string(),
        relation.to_string(),
        destination.to_string(),
        mech,
    );
    mapping.tenant_id = tenant_id.to_string();

    let mut lifecycle = inner.lifecycle.lock().map_err(|e| {
        PyRuntimeError::new_err(format!("Lifecycle lock poisoned: {}", e))
    })?;
    let episode = lifecycle.start_episode(mapping);
    Ok(episode.id.clone())
}

/// Advances a learning lifecycle episode to the next phase.
///
/// Phase must be one of: "proposed", "evidence_collected",
/// "consensus_resolved", "classified", "human_validation",
/// "committed", "deployed", "discarded", "compensated".
pub(crate) fn advance_episode(
    inner: &MemoryChipInner,
    episode_id: &str,
    phase: &str,
) -> PyResult<bool> {
    let target_phase = parse_lifecycle_phase(phase)?;
    let mut lifecycle = inner.lifecycle.lock().map_err(|e| {
        PyRuntimeError::new_err(format!("Lifecycle lock poisoned: {}", e))
    })?;

    // Verify episode exists
    if lifecycle.get(episode_id).is_none() {
        return Err(PyRuntimeError::new_err(format!(
            "Episode not found: {}",
            episode_id
        )));
    }

    // Execute phase transition
    match target_phase {
        LifecyclePhase::EvidenceCollected => {
            lifecycle.collect_evidence(episode_id).map_err(|e| {
                PyRuntimeError::new_err(format!("Phase advance failed: {}", e))
            })?;
        }
        LifecyclePhase::ConsensusResolved => {
            // May need to advance through intermediate phases
            lifecycle.collect_evidence(episode_id).ok();
            lifecycle.resolve_consensus(episode_id).map_err(|e| {
                PyRuntimeError::new_err(format!("Phase advance failed: {}", e))
            })?;
        }
        LifecyclePhase::Committed => {
            lifecycle.validate(episode_id);
        }
        LifecyclePhase::Deployed => {
            lifecycle.deploy(episode_id);
        }
        LifecyclePhase::Discarded => {
            lifecycle.discard(episode_id, "Discarded via advance_episode");
        }
        LifecyclePhase::Compensated => {
            lifecycle.compensate_simple(episode_id, "Compensated via advance_episode");
        }
        _ => {
            return Err(PyRuntimeError::new_err(format!(
                "Cannot advance to phase '{}' directly",
                phase
            )));
        }
    }

    Ok(true)
}
