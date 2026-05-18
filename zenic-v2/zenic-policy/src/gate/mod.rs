//! Criticality gates and safety vetoes for the policy engine.
//!
//! [`CriticalityGate`] enforces that a session has sufficient role
//! clearance to interact with nodes of a given criticality level.
//!
//! [`SafetyVeto`] implements immutable deny rules that can never be
//! overridden by any role or policy rule. Safety vetoes are the
//! hard boundary that protects the system from unsafe operations.

pub mod checker;
pub mod config;
pub mod types;

// Re-export all public API so that `gate::CriticalityGate` etc.
// continue to work without changes in the parent lib.rs.
pub use types::CriticalityGate;
pub use config::CriticalityGateBuilder;
pub use types::SafetyVeto;
pub use checker::SafetyVetoRegistry;
