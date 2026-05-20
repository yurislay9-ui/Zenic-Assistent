//! Policy engine: the main evaluation engine for access control.
//!
//! The [`PolicyEngine`] is the central component of the policy layer.
//! It coordinates RBAC permission checks, policy rule evaluation,
//! safety veto enforcement, and criticality gate checks. Every
//! access decision passes through the engine and is recorded in
//! the audit log.
//!
//! Evaluation order (first failure stops):
//! 1. Safety veto check — immutable deny rules.
//! 2. RBAC permission check — does any role grant the permission?
//! 3. Policy rule evaluation — explicit allow/deny rules.
//! 4. Criticality gate — sufficient clearance for the node?
//! 5. Default deny — if nothing matched, deny.

pub mod compiler;
pub mod evaluator;
pub mod optimizer;
pub mod types;

// Re-export all public items so that `crate::engine::PolicyEngine` and
// `crate::engine::PolicyContext` (and any other public symbol) remain
// accessible from the same import paths as before the split.
pub use compiler::*;
pub use evaluator::*;
pub use optimizer::*;
pub use types::*;
