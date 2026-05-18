//! Zero-copy rkyv evaluation (stub for Phase 3 integration).

use crate::audit::PolicyDecision;
use crate::errors::PolicyError;

use super::evaluator::PolicyEngine;

impl PolicyEngine {
    /// Evaluates a policy request using a pre-serialized rkyv byte buffer.
    ///
    /// This method performs zero-copy policy evaluation by using `rkyv::access`
    /// to read the archived evaluation context directly from shared memory,
    /// without deserializing the full context.
    ///
    /// **STUB**: Full integration will be in Phase 3 when the SharedMemoryBus
    /// uses rkyv for zero-copy transit. The eventual implementation will:
    /// 1. Use `rkyv::access::<ArchivedPolicyContext, rkyv::rancor::Error>(buffer)`
    ///    to obtain a zero-copy reference to the archived context.
    /// 2. Perform the same evaluation order (veto → RBAC → rules → gate).
    /// 3. Avoid allocating a full `PolicyContext` on the heap.
    pub fn evaluate_rkyv(&mut self, _buffer: &[u8]) -> Result<PolicyDecision, PolicyError> {
        // STUB: Phase 3 will implement zero-copy evaluation via rkyv::access.
        tracing::warn!(
            "evaluate_rkyv called but not yet implemented; \
             full integration arrives in Phase 3 (SharedMemoryBus)"
        );
        Err(PolicyError::General(
            "evaluate_rkyv is a stub — not yet integrated with SharedMemoryBus".to_string(),
        ))
    }
}
