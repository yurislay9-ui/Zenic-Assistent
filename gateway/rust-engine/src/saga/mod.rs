// ─── Zenic-Agents v3 — Saga Pattern for Subscription Engine ────────────
// USDT TRC20 ONLY. All subscription lifecycle operations are managed as
// Sagas with compensating actions for rollback on failure.

pub mod types;
pub mod definitions_core;
pub mod definitions_extended;
pub mod execution;
pub mod pricing;

pub use types::*;
pub use definitions_core::*;
pub use definitions_extended::get_saga_definition;
pub use execution::{create_saga_execution, advance_saga_step, complete_compensation_step};
pub use pricing::{ProrationResult, calculate_proration, validate_upgrade_path, validate_downgrade_path};
