//! Step executor trait.
//!
//! The [`StepExecutor`] trait abstracts the execution of a step so that
//! the flow engine remains independent of the runtime layer. The
//! `zenic-core` crate will implement this trait using
//! `zenic-runtime`'s DagScheduler.

use crate::step::WorkflowStep;

/// Trait for executing a single workflow step.
///
/// This trait abstracts the execution of a step so that the flow engine
/// remains independent of the runtime layer. The `zenic-core` crate
/// will implement this trait using `zenic-runtime`'s DagScheduler.
pub trait StepExecutor: Send + Sync {
    /// Executes a workflow step.
    ///
    /// - `step`: The step definition to execute.
    /// - `input`: Optional input data from the previous step's output.
    ///
    /// Returns the output data on success, or an error message on failure.
    fn execute_step(
        &self,
        step: &WorkflowStep,
        input: Option<&[u8]>,
    ) -> Result<Vec<u8>, String>;
}
