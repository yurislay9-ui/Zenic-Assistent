//! Rollback types and state machine definitions.

use pyo3::prelude::*;

/// Represent the lifecycle state of a coordinated action.
#[pyclass(name = "RollbackActionStatus", eq, eq_int)]
#[derive(Clone, Debug, PartialEq)]
pub enum RollbackActionStatus {
    InProgress,
    Committed,
    RolledBack,
}

/// Represent a resource type for rollback compensation.
#[pyclass(name = "RollbackResourceType", eq, eq_int)]
#[derive(Clone, Debug, PartialEq)]
pub enum RollbackResourceType {
    Db,
    Email,
    File,
    Webhook,
}
