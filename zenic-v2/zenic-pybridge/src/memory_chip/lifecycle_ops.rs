//! Memory Chip — PyO3 lifecycle, ontology, feature gate, and stats operations.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use zenic_memory::SemanticMapping;

use super::types::{
    MemoryChip, mem_err_to_py, parse_mechanism, parse_lifecycle_phase,
};

#[pymethods]
impl MemoryChip {
    // ─── Feature Gate ────────────────────────────────────────────

    /// Checks if a learning mechanism is allowed for the current tier.
    fn check_feature(&self, mechanism: &str, _tenant_id: &str) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let gate = inner.gate.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Gate lock poisoned: {}", e))
        })?;
        let mech = parse_mechanism(mechanism)?;
        Ok(gate.gate().is_mechanism_allowed(mech))
    }

    // ─── Learning Lifecycle ──────────────────────────────────────

    /// Starts a learning lifecycle episode.
    #[pyo3(signature = (origin, relation, destination, mechanism, tenant_id))]
    fn start_episode(
        &self,
        origin: &str,
        relation: &str,
        destination: &str,
        mechanism: &str,
        tenant_id: &str,
    ) -> PyResult<String> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

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
    fn advance_episode(&self, episode_id: &str, phase: &str) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

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
            zenic_memory::LifecyclePhase::EvidenceCollected => {
                lifecycle.collect_evidence(episode_id).map_err(|e| {
                    PyRuntimeError::new_err(format!("Phase advance failed: {}", e))
                })?;
            }
            zenic_memory::LifecyclePhase::ConsensusResolved => {
                lifecycle.collect_evidence(episode_id).ok();
                lifecycle.resolve_consensus(episode_id).map_err(|e| {
                    PyRuntimeError::new_err(format!("Phase advance failed: {}", e))
                })?;
            }
            zenic_memory::LifecyclePhase::Committed => {
                lifecycle.validate(episode_id);
            }
            zenic_memory::LifecyclePhase::Deployed => {
                lifecycle.deploy(episode_id);
            }
            zenic_memory::LifecyclePhase::Discarded => {
                lifecycle.discard(episode_id, "Discarded via advance_episode");
            }
            zenic_memory::LifecyclePhase::Compensated => {
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

    // ─── Ontology Search ─────────────────────────────────────────

    /// Searches the ontology base for terms matching a search string.
    fn search_ontology(&self, term: &str) -> PyResult<Vec<String>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let term_lower = term.to_lowercase();
        let results: Vec<String> = inner
            .ontology
            .all_mappings()
            .iter()
            .filter(|m| {
                m.origin.to_lowercase().contains(&term_lower)
                    || m.destination.to_lowercase().contains(&term_lower)
            })
            .map(|m| format!("{} → {} ({})", m.origin, m.destination, m.relation))
            .collect();

        Ok(results)
    }

    // ─── Statistics ──────────────────────────────────────────────

    /// Returns chip statistics as a dict.
    fn stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let cache_len = inner.cache.len();
        let cache_max = inner.cache.max_size();

        let total_mappings = {
            let graph = inner.graph.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
            })?;
            graph.count_mappings("__anonymous__").unwrap_or(0)
                + graph.count_mappings("__ontology_base__").unwrap_or(0)
        };

        let (pending_approvals, completed_approvals) = {
            let bridge = inner.hitl_bridge.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("HITL bridge lock poisoned: {}", e))
            })?;
            (bridge.pending_count(), bridge.completed_count())
        };

        let (sealed_count, merkle_root_hex) = {
            let seal = inner.merkle_seal.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Merkle seal lock poisoned: {}", e))
            })?;
            (seal.leaf_count(), seal.root_hash_hex())
        };

        let (verdict_total, verdict_ia, verdict_deterministic, verdict_escalations) = {
            let verdict = inner.verdict_adapter.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Verdict adapter lock poisoned: {}", e))
            })?;
            let s = verdict.stats();
            (s.total_verdicts, s.ia_verdicts, s.deterministic_verdicts, s.escalations)
        };

        let active_episodes = {
            let lifecycle = inner.lifecycle.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.len()
        };

        let result = PyDict::new_bound(py);
        result.set_item("cache_entries", cache_len)?;
        result.set_item("cache_max_size", cache_max)?;
        result.set_item("total_mappings", total_mappings)?;
        result.set_item("ontology_base_count", inner.ontology.base_count())?;
        result.set_item("pending_approvals", pending_approvals)?;
        result.set_item("completed_approvals", completed_approvals)?;
        result.set_item("sealed_mappings", sealed_count)?;
        result.set_item("active_episodes", active_episodes)?;
        result.set_item("verdict_total", verdict_total)?;
        result.set_item("verdict_ia", verdict_ia)?;
        result.set_item("verdict_deterministic", verdict_deterministic)?;
        result.set_item("verdict_escalations", verdict_escalations)?;
        result.set_item("merkle_root", merkle_root_hex)?;

        Ok(result.unbind())
    }
}
