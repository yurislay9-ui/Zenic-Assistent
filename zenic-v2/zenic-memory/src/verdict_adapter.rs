//! Verdict Adapter — Bridge a VerdictEngine.ask_yes_no() [T2-12, T3]
//!
//! The LLM NEVER generates content — only emits SÍ/NO verdicts.
//! The VerdictAdapter translates those verdicts into the appropriate
//! graph mutations, cache invalidations, or policy adjustments.
//!
//! Phase 3: Full integration with Qwen3-0.6B pattern.
//!
//! ## Qwen3-0.6B Integration Pattern
//!
//! The adapter formats a binary question for the LLM, which responds
//! with exactly 1 token: `SÍ` or `NO`. The adapter then:
//! 1. Parses the 1-token response
//! 2. Determines the appropriate action (commit, discard, escalate)
//! 3. Tracks verdict statistics for observability
//! 4. Integrates with HitlBridge for escalation flow

use crate::errors::MemoryError;
use crate::hitl_bridge::{HitlBridge, HitlOutcome};
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
// VerdictStatistics
// ---------------------------------------------------------------------------

/// Statistics tracked by the verdict adapter.
///
/// Provides observability into how often the IA is consulted vs.
/// deterministic resolution, and how often escalation occurs.
#[derive(Debug, Clone, Default)]
pub struct VerdictStatistics {
    /// Total number of verdicts processed.
    pub total_verdicts: u64,
    /// Verdicts resolved by the IA (Layer 4).
    pub ia_verdicts: u64,
    /// Verdicts resolved deterministically (Layer 1).
    pub deterministic_verdicts: u64,
    /// Verdicts escalated to human review.
    pub escalations: u64,
}

// ---------------------------------------------------------------------------
// FullVerdictResult
// ---------------------------------------------------------------------------

/// The full result of processing a verdict with mapping context.
///
/// Includes the action to take, whether HITL is needed, and optional
/// HITL bridge reference for escalation flow.
#[derive(Debug, Clone)]
pub struct FullVerdictResult {
    /// The action determined by the verdict.
    pub action: VerdictAction,
    /// Whether HITL (human-in-the-loop) review is required.
    pub requires_hitl: bool,
    /// The mapping that was evaluated.
    pub mapping: SemanticMapping,
    /// The verdict that was processed.
    pub verdict: LearningVerdict,
    /// Optional HITL outcome if escalation was resolved immediately.
    pub hitl_outcome: Option<HitlOutcome>,
}

// ---------------------------------------------------------------------------
// LlmResponse
// ---------------------------------------------------------------------------

/// Parsed response from the LLM (1-token: SÍ/NO).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LlmResponse {
    /// The LLM answered YES (affirmative).
    Yes,
    /// The LLM answered NO (negative).
    No,
}

impl LlmResponse {
    /// Parses a 1-token LLM response string.
    ///
    /// Accepts "SÍ", "SI", "YES", "Y" as affirmative.
    /// Accepts "NO", "N" as negative.
    /// Case-insensitive, trims whitespace.
    pub fn parse(token: &str) -> Result<Self, MemoryError> {
        let normalized = token.trim().to_uppercase();
        // Handle "SÍ" with accent and "SI" without
        match normalized.as_str() {
            "SÍ" | "SI" | "YES" | "Y" | "1" | "TRUE" => Ok(Self::Yes),
            "NO" | "N" | "0" | "FALSE" => Ok(Self::No),
            _ => Err(MemoryError::VerdictRejected(format!(
                "Invalid LLM token '{}': expected SÍ/NO (1 token)",
                token.trim()
            ))),
        }
    }

    /// Returns `true` if the response is affirmative.
    pub fn is_yes(self) -> bool {
        matches!(self, Self::Yes)
    }
}

// ---------------------------------------------------------------------------
// Qwen3Prompt
// ---------------------------------------------------------------------------

/// Formatted prompt for the Qwen3-0.6B model.
///
/// The model is instructed to respond with exactly 1 token.
/// No generation — only classification.
#[derive(Debug, Clone)]
pub struct Qwen3Prompt {
    /// The system instruction that constrains the model.
    pub system_prompt: String,
    /// The binary question for the model.
    pub user_prompt: String,
}

// ---------------------------------------------------------------------------
// VerdictAdapter
// ---------------------------------------------------------------------------

/// Adapter that converts LLM boolean verdicts into memory chip actions.
///
/// Uses the Adapter pattern to translate between the verdict pipeline
/// and the memory chip's internal operations.
///
/// ## Design
///
/// The adapter maintains:
/// - Verdict statistics for observability
/// - Integration with `HitlBridge` for escalation flow
/// - A `process_full_verdict()` method that takes a `SemanticMapping` +
///   `LearningVerdict` and returns the full action including HITL status
pub struct VerdictAdapter {
    /// The last verdict processed.
    last_verdict: Option<LearningVerdict>,
    /// Statistics tracking verdict outcomes.
    stats: VerdictStatistics,
    /// HITL bridge for escalation flow.
    hitl_bridge: HitlBridge,
}

impl VerdictAdapter {
    /// Creates a new verdict adapter.
    pub fn new() -> Self {
        Self {
            last_verdict: None,
            stats: VerdictStatistics::default(),
            hitl_bridge: HitlBridge::new(),
        }
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
        self.stats.total_verdicts += 1;

        if verdict.is_deterministic() {
            // Layer 1 resolved — no IA needed, auto-commit
            self.stats.deterministic_verdicts += 1;
            VerdictAction::CommitMapping
        } else if verdict.ia_response {
            // IA said YES → commit (but needs HITL for Layer 4)
            self.stats.ia_verdicts += 1;
            VerdictAction::CommitMapping
        } else if verdict.consensus_score.abs() < 0.1 {
            // Tie → escalate to human
            self.stats.escalations += 1;
            VerdictAction::EscalateToHuman
        } else {
            // IA said NO → discard
            self.stats.ia_verdicts += 1;
            VerdictAction::DiscardMapping
        }
    }

    /// Processes a full verdict with mapping context.
    ///
    /// Takes a `SemanticMapping` + `LearningVerdict` and returns the
    /// full action including whether HITL is needed. If escalation is
    /// required, the verdict is automatically submitted to the HITL bridge.
    ///
    /// This is the primary entry point for Phase 3 integration.
    pub fn process_full_verdict(
        &mut self,
        mapping: SemanticMapping,
        verdict: LearningVerdict,
    ) -> FullVerdictResult {
        let action = self.process_verdict(verdict.clone());
        let requires_hitl = action == VerdictAction::EscalateToHuman
            || (!verdict.is_deterministic() && verdict.ia_response);

        let hitl_outcome = if action == VerdictAction::EscalateToHuman {
            // Submit to HITL bridge for escalation
            let request = HitlBridge::create_request_from_verdict(
                &verdict,
                "__pending_admin__".to_string(),
            );
            if let Err(e) = self.hitl_bridge.submit_for_review(request) {
                tracing::warn!("HITL submission failed: {}", e);
            }
            None // Still pending admin action
        } else {
            None
        };

        FullVerdictResult {
            action,
            requires_hitl,
            mapping,
            verdict,
            hitl_outcome,
        }
    }

    /// Constructs a binary YES/NO question for the IA.
    ///
    /// The IA only answers with 1 token: SÍ or NO.
    pub fn construct_binary_question(mapping: &SemanticMapping) -> String {
        mapping.binary_question()
    }

    /// Formats a Qwen3-0.6B prompt from a semantic mapping.
    ///
    /// The system prompt constrains the model to respond with exactly
    /// 1 token (SÍ/NO), and the user prompt contains the binary question.
    pub fn format_qwen3_prompt(mapping: &SemanticMapping) -> Qwen3Prompt {
        Qwen3Prompt {
            system_prompt: "Eres un clasificador binario. Respondes con exactamente un token: SÍ o NO. No generas contenido, solo clasificas.".to_string(),
            user_prompt: Self::construct_binary_question(mapping),
        }
    }

    /// Parses a 1-token LLM response (SÍ/NO) into a boolean verdict.
    ///
    /// This is the bridge between the Qwen3-0.6B output and the
    /// verdict pipeline's internal representation.
    pub fn parse_llm_response(token: &str) -> Result<bool, MemoryError> {
        LlmResponse::parse(token).map(|r| r.is_yes())
    }

    /// Returns the last processed verdict.
    pub fn last_verdict(&self) -> Option<&LearningVerdict> {
        self.last_verdict.as_ref()
    }

    /// Returns a reference to the verdict statistics.
    pub fn stats(&self) -> &VerdictStatistics {
        &self.stats
    }

    /// Returns a reference to the HITL bridge.
    pub fn hitl_bridge(&self) -> &HitlBridge {
        &self.hitl_bridge
    }

    /// Returns a mutable reference to the HITL bridge.
    pub fn hitl_bridge_mut(&mut self) -> &mut HitlBridge {
        &mut self.hitl_bridge
    }

    /// Resets the verdict statistics.
    pub fn reset_stats(&mut self) {
        self.stats = VerdictStatistics::default();
    }
}

impl Default for VerdictAdapter {
    fn default() -> Self {
        Self::new()
    }
}
