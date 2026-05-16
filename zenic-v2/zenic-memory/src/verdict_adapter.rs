//! Verdict Adapter — Bridge a VerdictEngine.ask_yes_no() [T2-12, T3]
//!
//! The LLM NEVER generates content — only emits SÍ/NO verdicts.
//! The VerdictAdapter translates those verdicts into the appropriate
//! graph mutations, cache invalidations, or policy adjustments.
//!
//! Phase 3: Full integration with Qwen3-0.6B pending.

use crate::types::{LearningVerdict, SemanticMapping};

// ---------------------------------------------------------------------------
// VerdictAction
// ---------------------------------------------------------------------------

/// Action to take based on an LLM verdict.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VerdictAction {
    /// Commit the proposed mapping to the semantic graph.
    CommitMapping,
    /// Discard the proposed mapping.
    DiscardMapping,
    /// Escalate to human review (tie/consensus failure).
    EscalateToHuman,
}

// ---------------------------------------------------------------------------
// VerdictAdapter
// ---------------------------------------------------------------------------

/// Adapter that converts LLM boolean verdicts into memory chip actions.
pub struct VerdictAdapter {
    /// The last verdict processed.
    last_verdict: Option<LearningVerdict>,
}

impl VerdictAdapter {
    /// Creates a new verdict adapter.
    pub fn new() -> Self {
        Self { last_verdict: None }
    }

    /// Processes a verdict from the 4-layer classification pipeline.
    ///
    /// Maps the verdict result to an action:
    /// - Layer 1 deterministic → CommitMapping (no IA needed)
    /// - Layer 4 IA YES → CommitMapping
    /// - Layer 4 IA NO → DiscardMapping
    /// - Tie/consensus failure → EscalateToHuman
    pub fn process_verdict(&mut self, verdict: LearningVerdict) -> VerdictAction {
        self.last_verdict = Some(verdict.clone());

        if verdict.is_deterministic() {
            // Layer 1 resolved — no IA needed, auto-commit
            VerdictAction::CommitMapping
        } else if verdict.ia_response {
            // IA said YES → commit (but needs HITL for Layer 4)
            VerdictAction::CommitMapping
        } else if verdict.consensus_score.abs() < 0.1 {
            // Tie → escalate to human
            VerdictAction::EscalateToHuman
        } else {
            // IA said NO → discard
            VerdictAction::DiscardMapping
        }
    }

    /// Returns the last processed verdict.
    pub fn last_verdict(&self) -> Option<&LearningVerdict> {
        self.last_verdict.as_ref()
    }

    /// Constructs a binary YES/NO question for the IA.
    ///
    /// The IA only answers with 1 token: SÍ or NO.
    pub fn construct_binary_question(mapping: &SemanticMapping) -> String {
        mapping.binary_question()
    }
}

impl Default for VerdictAdapter {
    fn default() -> Self {
        Self::new()
    }
}
