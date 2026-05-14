//! # zenic-core
//!
//! Main orchestrator with fractal loader and hierarchical router for Zenic-Agents.
//!
//! This crate is the top-level entry point for the entire system. It
//! integrates all subsystems and provides high-level operations:
//!
//! - [`Orchestrator`] — owns all subsystems and coordinates operations
//! - [`OrchestratorConfig`] — tuneable parameters for the orchestrator
//! - [`Session`] / [`SessionStore`] — session lifecycle management
//! - [`RequestRouter`] / [`RouteDecision`] — request classification
//! - [`DagStepExecutor`] — bridges workflow steps to the DAG scheduler
//! - [`CoreError`] — unified error type wrapping all subsystem errors
//!
//! Every operation flows through the orchestrator, which enforces:
//! 1. Session validation
//! 2. Policy check (is the session allowed to do this?)
//! 3. Subsystem execution
//! 4. Result return

pub mod config;
pub mod errors;
pub mod orchestrator;
pub mod router;
pub mod session;
pub mod step_bridge;

// Convenience re-exports: allow `zenic_core::Orchestrator` instead of
// `zenic_core::orchestrator::Orchestrator`.
pub use config::OrchestratorConfig;
pub use errors::CoreError;
pub use orchestrator::{Orchestrator, OrchestratorStatus};
pub use router::{RouteAction, RouteDecision, RequestRouter};
pub use session::{Session, SessionStore};
pub use step_bridge::DagStepExecutor;
