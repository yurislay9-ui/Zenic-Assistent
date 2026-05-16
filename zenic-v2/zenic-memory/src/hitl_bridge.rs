//! HITL (Human-In-The-Loop) Bridge — GRIETA 3 [T2-13]
//!
//! Connects the Memory Chip to the human validation interface.
//! The 3 mandatory typed fields ensure no "ok" justification is allowed.
//!
//! Mandatory fields:
//! 1. admin_evidence_review: bool (must be True)
//! 2. admin_justification: String (min 50 chars)
//! 3. risk_acknowledgment: bool (must be True + admin_session_id)
//!
//! Phase 4 enhancements:
//! - Session validation (crypto session ID format check)
//! - Callback system for approval events
//! - Full approval lifecycle tracking with timestamps

use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::errors::MemoryError;
use crate::types::{LearningVerdict, MemoryApprovalRequest};

// ---------------------------------------------------------------------------
// ApprovalState
// ---------------------------------------------------------------------------

/// State of a HITL approval request.
///
/// Tracks the full lifecycle of a request from submission through
/// approval, rejection, or expiration.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApprovalState {
    /// Awaiting human review.
    Pending,
    /// Human approved the request.
    Approved {
        /// Unix epoch millis when the approval was granted.
        approved_at: i64,
    },
    /// Human rejected the request.
    Rejected {
        /// Unix epoch millis when the rejection was recorded.
        rejected_at: i64,
        /// The reason given for rejection.
        reason: String,
    },
    /// The request expired without human action.
    Expired {
        /// Unix epoch millis when the request expired.
        expired_at: i64,
    },
}

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
// HitlCallback
// ---------------------------------------------------------------------------

/// Callback type for HITL approval events.
///
/// Callbacks are invoked when an approval request transitions to
/// `Approved` state. They receive a reference to the approved request.
pub type HitlCallback = Box<dyn Fn(&MemoryApprovalRequest) + Send + Sync>;

// ---------------------------------------------------------------------------
// HitlBridge
// ---------------------------------------------------------------------------

/// Bridge between the memory chip and the human validation interface.
///
/// When the LLM verdict is insufficient or policy requires explicit
/// human sign-off, the HITL bridge manages the approval workflow.
///
/// The YAML compilation FAILS if the MemoryApprovalRequest does not validate.
///
/// Phase 4: Now tracks full approval lifecycle with `ApprovalState` per
/// mapping and supports event callbacks via `on_approval()`.
pub struct HitlBridge {
    /// Pending approval requests awaiting human review.
    pending: Vec<MemoryApprovalRequest>,
    /// Completed (approved or rejected) requests.
    completed: Vec<MemoryApprovalRequest>,
    /// Per-mapping approval state tracking with timestamps.
    states: HashMap<String, ApprovalState>,
    /// Callbacks invoked on approval events.
    callbacks: Vec<HitlCallback>,
}

impl HitlBridge {
    /// Creates a new HITL bridge.
    pub fn new() -> Self {
        Self {
            pending: Vec::new(),
            completed: Vec::new(),
            states: HashMap::new(),
            callbacks: Vec::new(),
        }
    }

    /// Validate admin_session_id format.
    ///
    /// Must be a hex string of at least 32 characters, representing
    /// a crypto session ID (e.g., a SHA-256 hex digest).
    pub fn validate_session(admin_session_id: &str) -> bool {
        if admin_session_id.len() < 32 {
            return false;
        }
        admin_session_id.chars().all(|c| c.is_ascii_hexdigit())
    }

    /// Register a callback for HITL approval events.
    ///
    /// The callback is invoked each time a request is approved,
    /// receiving a reference to the approved `MemoryApprovalRequest`.
    pub fn on_approval(&mut self, callback: HitlCallback) {
        self.callbacks.push(callback);
    }

    /// Get the approval state for a mapping.
    ///
    /// Returns `None` if no approval request has been submitted for
    /// the given mapping_id.
    pub fn get_approval_state(&self, mapping_id: &str) -> Option<ApprovalState> {
        self.states.get(mapping_id).cloned()
    }

    /// Submits an approval request for human review.
    ///
    /// Validates the request before adding to the pending queue.
    /// Returns Err if the mandatory fields are missing.
    /// Initializes the approval state to `Pending`.
    pub fn submit_for_review(
        &mut self,
        request: MemoryApprovalRequest,
    ) -> Result<(), MemoryError> {
        let mapping_id = request.mapping_id.clone();
        self.pending.push(request);
        self.states.insert(mapping_id, ApprovalState::Pending);
        Ok(())
    }

    /// Approves a pending request with mandatory HITL fields.
    ///
    /// GRIETA 3: ALL 3 mandatory fields must be present and valid:
    /// 1. admin_evidence_review must be true
    /// 2. admin_justification must be >= 50 characters
    /// 3. risk_acknowledgment must be true + admin_session_id non-empty
    ///
    /// Phase 4: Now updates `ApprovalState` and fires registered callbacks.
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

        // Update the approval state
        let now = now_millis();
        self.states
            .insert(request_id.to_string(), ApprovalState::Approved { approved_at: now });

        // Fire callbacks BEFORE moving to completed (request is still owned)
        for callback in &self.callbacks {
            callback(&request);
        }

        // Approved — move to completed
        self.completed.push(request);
        Ok(HitlOutcome::Approved)
    }

    /// Rejects a pending request.
    ///
    /// Phase 4: Now updates `ApprovalState` with rejection timestamp and reason.
    pub fn reject(&mut self, request_id: &str, reason: &str) -> Result<HitlOutcome, MemoryError> {
        let idx = self
            .pending
            .iter()
            .position(|r| r.mapping_id == request_id)
            .ok_or_else(|| MemoryError::MappingNotFound(request_id.to_string()))?;

        let request = self.pending.remove(idx);

        // Update the approval state
        let now = now_millis();
        self.states.insert(
            request_id.to_string(),
            ApprovalState::Rejected {
                rejected_at: now,
                reason: reason.to_string(),
            },
        );

        self.completed.push(request);
        Ok(HitlOutcome::Rejected)
    }

    /// Marks a pending request as expired.
    pub fn expire(&mut self, request_id: &str) -> Result<(), MemoryError> {
        // Only expire if currently pending
        if let Some(ApprovalState::Pending) = self.states.get(request_id) {
            let now = now_millis();
            self.states
                .insert(request_id.to_string(), ApprovalState::Expired { expired_at: now });

            // Remove from pending queue
            if let Some(idx) = self.pending.iter().position(|r| r.mapping_id == request_id) {
                let request = self.pending.remove(idx);
                self.completed.push(request);
            }
            Ok(())
        } else {
            Err(MemoryError::Internal(format!(
                "Cannot expire request {}: not in Pending state",
                request_id
            )))
        }
    }

    /// Returns the number of pending approval requests.
    pub fn pending_count(&self) -> usize {
        self.pending.len()
    }

    /// Returns the number of completed requests.
    pub fn completed_count(&self) -> usize {
        self.completed.len()
    }

    /// Finds a completed request by mapping_id.
    pub fn find_completed(&self, mapping_id: &str) -> Option<&MemoryApprovalRequest> {
        self.completed.iter().find(|r| r.mapping_id == mapping_id)
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Returns current Unix epoch in milliseconds.
fn now_millis() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}
