//! # zenic-flow
//!
//! Durable workflow engine with checkpoints, SAGA compensation, and retry
//! with exponential backoff for Zenic-Agents.
//!
//! This crate provides:
//! - [`WorkflowEngine`] — main orchestrator for durable workflow execution
//! - [`WorkflowDefinition`] / [`WorkflowInstance`] — workflow blueprint and runtime state
//! - [`StepExecutor`] — trait for step execution (implemented by zenic-core)
//! - [`Checkpoint`] / [`CheckpointStore`] — durability via snapshot + restore
//! - [`CompensationRegistry`] / [`CompensationAction`] — SAGA pattern
//! - [`RetryPolicy`] — exponential backoff configuration
//! - [`WorkflowStatus`] / [`StepStatus`] — state machine enums
//! - [`WorkflowStep`] / [`StepResult`] — step definition and outcome

pub mod checkpoint;
pub mod compensation;
pub mod engine;
pub mod errors;
pub mod retry;
pub mod status;
pub mod step;

// Convenience re-exports.
pub use checkpoint::Checkpoint;
pub use compensation::{CompensationAction, CompensationRegistry, NoOpCompensation};
pub use engine::{
    CheckpointStore, StepExecutor, WorkflowDefinition, WorkflowEngine, WorkflowInstance,
};
pub use errors::FlowError;
pub use retry::RetryPolicy;
pub use status::{StepStatus, WorkflowStatus};
pub use step::{StepResult, WorkflowStep};
