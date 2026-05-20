//! Lifecycle phase transitions — the main `LifecycleOrchestrator` methods.
//!
//! Contains the `impl LifecycleOrchestrator` block for constructing the
//! orchestrator and running episodes through their phase transitions.

use std::sync::{Arc, Mutex};

use crate::cache::MemoryCache;
use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::hitl_bridge::HitlBridge;
use crate::merkle_seal::MerkleSeal;
use crate::subscription_gate::SubscriptionGate;
use crate::types::{
    LearningMechanism, LearningVerdict, MemoryApprovalRequest, SemanticMapping, SubscriptionTier,
};
use crate::yaml_renderer::YamlRenderer;

use super::manager::LifecycleManager;
use super::types::{CompensationAction, EpisodeOutcome, EpisodeResult, LifecyclePhase};

use super::LifecycleOrchestrator;

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
    pub(super) fn complete_episode_internal(
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
}
