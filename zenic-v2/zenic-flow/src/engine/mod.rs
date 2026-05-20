//! Workflow engine: orchestrates durable workflow execution with
//! checkpoints, SAGA compensation, and retry with exponential backoff.
//!
//! The [`WorkflowEngine`] is the main entry point for executing durable
//! workflows. It coordinates:
//! - Sequential step execution through the [`StepExecutor`] trait
//! - Checkpoint persistence after each step
//! - Retry with configurable backoff policies
//! - SAGA compensation on unrecoverable failure
//!
//! The engine does NOT depend on `zenic-runtime` directly. The
//! [`StepExecutor`] trait abstracts step execution so that `zenic-core`
//! can provide an implementation backed by the runtime's DagScheduler.

pub mod definition;
pub mod executor;
pub mod instance;
pub mod store;
#[cfg(test)]
mod tests;
pub mod workflow_engine;

// Re-export all public types so that `crate::engine::T` still works.
pub use definition::WorkflowDefinition;
pub use executor::StepExecutor;
pub use instance::WorkflowInstance;
pub use store::CheckpointStore;
pub use workflow_engine::WorkflowEngine;
