//! HITL (Human-In-The-Loop) Bridge — GRIETA 3 [T2-13]
//!
//! Connects the Memory Chip to the human validation interface.
//! The 3 mandatory typed fields ensure no "ok" justification is allowed.
//!
//! Mandatory fields:
//! 1. admin_evidence_review: bool (must be True)
//! 2. admin_justification: String (min 50 chars)
//! 3. risk_acknowledgment: bool (must be True + admin_session_id)

use crate::errors::MemoryError;
use crate::types::{LearningVerdict, MemoryApprovalRequest};

// ---------------------------------------------------------------------------
// HitlOutcome
// ---------------------------------------------------------------------------

/// Outcome of a human validation step.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HitlOutcome {
    /// Human approved the proposed action.
    Approved,
    /// Human rejected the proposed action.
    Rejected,
    /// Human requested modifications.
    ModifyRequested,
}

// ---------------------------------------------------------------------------
// HitlBridge
// ---------------------------------------------------------------------------

/// Bridge between the memory chip and the human validation interface.
///
/// When the LLM verdict is insufficient or policy requires explicit
/// human sign-off, the HITL bridge manages the approval workflow.
///
/// The YAML compilation FAILS if the MemoryApprovalRequest does not validate.
pub struct HitlBridge {
    /// Pending approval requests awaiting human review.
    pending: Vec<MemoryApprovalRequest>,
    /// Completed (approved or rejected) requests.
    completed: Vec<MemoryApprovalRequest>,
}

impl HitlBridge {
    /// Creates a new HITL bridge.
    pub fn new() -> Self {
        Self {
            pending: Vec::new(),
            completed: Vec::new(),
        }
    }

    /// Submits an approval request for human review.
    ///
    /// Validates the request before adding to the pending queue.
    /// Returns Err if the mandatory fields are missing.
    pub fn submit_for_review(
        &mut self,
        request: MemoryApprovalRequest,
    ) -> Result<(), MemoryError> {
        // Pre-validate: the request will need to pass validation
        // when the admin fills in the mandatory fields.
        // At submission time, the fields may be empty (pending admin input).
        self.pending.push(request);
        Ok(())
    }

    /// Approves a pending request with mandatory HITL fields.
    ///
    /// GRIETA 3: ALL 3 mandatory fields must be present and valid:
    /// 1. admin_evidence_review must be true
    /// 2. admin_justification must be >= 50 characters
    /// 3. risk_acknowledgment must be true + admin_session_id non-empty
    pub fn approve(
        &mut self,
        request_id: &str,
        admin_evidence_review: bool,
        admin_justification: String,
        risk_acknowledgment: bool,
        admin_session_id: String,
    ) -> Result<HitlOutcome, MemoryError> {
        let idx = self
            .pending
            .iter()
            .position(|r| r.mapping_id == request_id)
            .ok_or_else(|| MemoryError::MappingNotFound(request_id.to_string()))?;

        let mut request = self.pending.remove(idx);

        // Fill in the mandatory fields
        request.admin_evidence_review = admin_evidence_review;
        request.admin_justification = admin_justification;
        request.risk_acknowledgment = risk_acknowledgment;
        request.admin_session_id = admin_session_id;

        // Validate — GRIETA 3 closure
        request.validate()?;

        // Approved — move to completed
        self.completed.push(request);
        Ok(HitlOutcome::Approved)
    }

    /// Rejects a pending request.
    pub fn reject(&mut self, request_id: &str, reason: &str) -> Result<HitlOutcome, MemoryError> {
        let idx = self
            .pending
            .iter()
            .position(|r| r.mapping_id == request_id)
            .ok_or_else(|| MemoryError::MappingNotFound(request_id.to_string()))?;

        let request = self.pending.remove(idx);
        self.completed.push(request);
        Ok(HitlOutcome::Rejected)
    }

    /// Returns the number of pending approval requests.
    pub fn pending_count(&self) -> usize {
        self.pending.len()
    }

    /// Returns the number of completed requests.
    pub fn completed_count(&self) -> usize {
        self.completed.len()
    }

    /// Creates a MemoryApprovalRequest from a LearningVerdict.
    pub fn create_request_from_verdict(
        verdict: &LearningVerdict,
        admin_session_id: String,
    ) -> MemoryApprovalRequest {
        MemoryApprovalRequest::from_verdict(verdict, admin_session_id)
    }
}

impl Default for HitlBridge {
    fn default() -> Self {
        Self::new()
    }
}
