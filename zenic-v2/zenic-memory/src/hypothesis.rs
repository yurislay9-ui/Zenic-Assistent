//! Hypothesis Generator — "La Capa Estructurada Propone" [T1-10]
//!
//! The HypothesisManager generates hypotheses from the deterministic layer
//! that will be classified by the IA (SÍ/NO) and validated by a human.
//!
//! Flow: Deterministic Layer → HypothesisGenerator → IA YES/NO → HITL → Memory Graph

use crate::errors::MemoryError;
use crate::types::{Hypothesis, LearningMechanism};

// ---------------------------------------------------------------------------
// HypothesisManager
// ---------------------------------------------------------------------------

/// Manages the hypothesis lifecycle: generation, classification, validation.
///
/// Hypotheses are proposed by the deterministic layer when it detects
/// friction (low confidence, missing field, ambiguous intent). They
/// await IA classification (YES/NO) and human validation before
/// being committed to the semantic graph.
pub struct HypothesisManager {
    /// Pending hypotheses awaiting classification.
    pending: Vec<Hypothesis>,
    /// Classified hypotheses awaiting HITL.
    classified: Vec<ClassifiedHypothesis>,
    /// Maximum pending hypotheses before rejection.
    max_pending: usize,
}

/// A hypothesis that has been classified by the IA.
#[derive(Debug, Clone)]
pub struct ClassifiedHypothesis {
    /// The original hypothesis.
    pub hypothesis: Hypothesis,
    /// IA verdict: true = YES (accept), false = NO (reject).
    pub ia_response: bool,
    /// Evidence in favor.
    pub evidence_for: Vec<String>,
    /// Evidence against.
    pub evidence_against: Vec<String>,
    /// Consensus score from the resolver.
    pub consensus_score: f64,
}

impl HypothesisManager {
    /// Creates a new hypothesis manager with default capacity.
    pub fn new() -> Self {
        Self {
            pending: Vec::with_capacity(64),
            classified: Vec::with_capacity(64),
            max_pending: 1000,
        }
    }

    /// Creates a new hypothesis manager with custom capacity.
    pub fn with_capacity(max_pending: usize) -> Self {
        Self {
            pending: Vec::with_capacity(64),
            classified: Vec::with_capacity(64),
            max_pending,
        }
    }

    /// Generates a Schema Drift hypothesis.
    ///
    /// Mechanism 1: DB column renames — "estatus_cliente → estado_id"
    pub fn generate_schema_drift(
        &mut self,
        original_field: &str,
        expected_field: &str,
        context: &str,
    ) -> Result<&Hypothesis, MemoryError> {
        self.ensure_capacity()?;
        let hypothesis = Hypothesis::new(
            original_field,
            "maps_to",
            expected_field,
            LearningMechanism::SchemaDrift,
            context,
            0.5, // Initial confidence before IA
        );
        self.pending.push(hypothesis);
        Ok(self.pending.last().unwrap())
    }

    /// Generates an Intent Routing hypothesis.
    ///
    /// Mechanism 2: Ambiguous user intent → MCP tool matching
    /// "tumba la cuenta → cancelar_suscripcion"
    pub fn generate_intent_routing(
        &mut self,
        user_intent: &str,
        mcp_tool: &str,
        context: &str,
    ) -> Result<&Hypothesis, MemoryError> {
        self.ensure_capacity()?;
        let hypothesis = Hypothesis::new(
            user_intent,
            "routes_to",
            mcp_tool,
            LearningMechanism::IntentRouting,
            context,
            0.4, // Lower confidence for ambiguous intents
        );
        self.pending.push(hypothesis);
        Ok(self.pending.last().unwrap())
    }

    /// Generates a Policy Refinement hypothesis.
    ///
    /// Mechanism 3: Gray-area classification — "reparación urgente → gasto_crítico"
    pub fn generate_policy_refinement(
        &mut self,
        original_term: &str,
        refined_category: &str,
        context: &str,
    ) -> Result<&Hypothesis, MemoryError> {
        self.ensure_capacity()?;
        let hypothesis = Hypothesis::new(
            original_term,
            "classifies_as",
            refined_category,
            LearningMechanism::PolicyRefinement,
            context,
            0.3, // Lowest confidence for gray areas
        );
        self.pending.push(hypothesis);
        Ok(self.pending.last().unwrap())
    }

    /// Classifies a hypothesis with an IA verdict.
    ///
    /// Moves it from pending to classified queue.
    pub fn classify(
        &mut self,
        hypothesis_idx: usize,
        ia_response: bool,
        evidence_for: Vec<String>,
        evidence_against: Vec<String>,
        consensus_score: f64,
    ) -> Result<(), MemoryError> {
        if hypothesis_idx >= self.pending.len() {
            return Err(MemoryError::HypothesisFailed(
                "Invalid hypothesis index".to_string(),
            ));
        }

        let hypothesis = self.pending.remove(hypothesis_idx);
        self.classified.push(ClassifiedHypothesis {
            hypothesis,
            ia_response,
            evidence_for,
            evidence_against,
            consensus_score,
        });

        Ok(())
    }

    /// Gets the next classified hypothesis awaiting HITL validation.
    pub fn next_for_hitl(&self) -> Option<&ClassifiedHypothesis> {
        // Return the first IA-accepted hypothesis that needs human validation
        self.classified.iter().find(|ch| ch.ia_response)
    }

    /// Removes a classified hypothesis after HITL resolution.
    pub fn resolve(&mut self, hypothesis_origin: &str) -> Option<ClassifiedHypothesis> {
        let idx = self
            .classified
            .iter()
            .position(|ch| ch.hypothesis.origin == hypothesis_origin)?;
        Some(self.classified.remove(idx))
    }

    /// Returns the number of pending hypotheses.
    pub fn pending_count(&self) -> usize {
        self.pending.len()
    }

    /// Returns the number of classified hypotheses awaiting HITL.
    pub fn classified_count(&self) -> usize {
        self.classified.len()
    }

    /// Returns all pending hypotheses.
    pub fn pending(&self) -> &[Hypothesis] {
        &self.pending
    }

    /// Returns all classified hypotheses.
    pub fn classified(&self) -> &[ClassifiedHypothesis] {
        &self.classified
    }

    /// Clears all hypotheses.
    pub fn clear(&mut self) {
        self.pending.clear();
        self.classified.clear();
    }

    /// Ensures we don't exceed capacity.
    fn ensure_capacity(&self) -> Result<(), MemoryError> {
        if self.pending.len() >= self.max_pending {
            return Err(MemoryError::HypothesisFailed(format!(
                "Hypothesis queue full (max {})", self.max_pending
            )));
        }
        Ok(())
    }
}

impl Default for HypothesisManager {
    fn default() -> Self {
        Self::new()
    }
}
