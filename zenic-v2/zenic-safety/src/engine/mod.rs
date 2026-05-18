//! Domain Safety Gate — 4-layer safety validation pipeline.
//!
//! Layer 1: Base SafetyGate (10 generic rules)
//! Layer 2: Domain-specific rules (35 = 5 per NicheCategory)
//! Layer 3: Compliance validation (8 standards)
//! Layer 4: Sensitivity escalation (critical → auto-deny)
//!
//! INVARIANTS:
//!   1. Domain rules can only ESCALATE verdicts, never downgrade.
//!   2. If the base gate returns DENY, domain gate CANNOT override.
//!   3. Compliance failures for critical violations result in DENY.
//!   4. All logic is deterministic — no AI, no randomness.

pub mod checks;
pub mod core;
pub mod types;

// Re-export the primary public types so the parent crate can reference engine::*
pub use core::DomainSafetyGate;
pub use types::DomainSafetyCheckResult;
