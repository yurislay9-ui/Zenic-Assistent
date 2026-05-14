//! Orchestrator configuration for Zenic-Agents.
//!
//! [`OrchestratorConfig`] holds all tuneable parameters for the
//! orchestrator: memory limits, default retry policies, and
//! feature flags. The config is validated at construction time
//! and passed to the orchestrator on startup.

use zenic_flow::RetryPolicy;
use zenic_runtime::{DEFAULT_MAX_LOADED_NODES, DEFAULT_MEMORY_BUDGET_BYTES};

use crate::errors::CoreError;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Default maximum number of concurrent sessions.
pub const DEFAULT_MAX_SESSIONS: usize = 100;

// ---------------------------------------------------------------------------
// OrchestratorConfig
// ---------------------------------------------------------------------------

/// Configuration for the Zenic-Agents orchestrator.
///
/// This struct is the single place to tune the orchestrator's behavior.
/// It is validated at construction time to catch misconfigurations early.
/// Once validated, it is passed to [`crate::orchestrator::Orchestrator::new`].
#[derive(Debug, Clone)]
pub struct OrchestratorConfig {
    /// Maximum number of nodes that can be loaded in RAM simultaneously.
    /// Defaults to [`DEFAULT_MAX_LOADED_NODES`] (25).
    pub max_loaded_nodes: usize,

    /// Maximum total memory budget in bytes for loaded nodes.
    /// Defaults to [`DEFAULT_MEMORY_BUDGET_BYTES`] (50 MB).
    pub memory_budget_bytes: u64,

    /// Default retry policy for durable workflows.
    /// Applied to workflow steps that do not have their own override.
    pub default_retry_policy: RetryPolicy,

    /// Maximum number of concurrent sessions allowed.
    /// New sessions beyond this limit are rejected.
    pub max_sessions: usize,
}

impl OrchestratorConfig {
    /// Creates a new config with default values.
    pub fn new() -> Self {
        Self {
            max_loaded_nodes: DEFAULT_MAX_LOADED_NODES,
            memory_budget_bytes: DEFAULT_MEMORY_BUDGET_BYTES,
            default_retry_policy: RetryPolicy::default(),
            max_sessions: DEFAULT_MAX_SESSIONS,
        }
    }

    /// Creates a config with custom memory limits.
    pub fn with_memory_limits(max_loaded_nodes: usize, memory_budget_bytes: u64) -> Self {
        Self {
            max_loaded_nodes,
            memory_budget_bytes,
            default_retry_policy: RetryPolicy::default(),
            max_sessions: DEFAULT_MAX_SESSIONS,
        }
    }

    /// Sets the default retry policy.
    pub fn with_retry_policy(mut self, policy: RetryPolicy) -> Self {
        self.default_retry_policy = policy;
        self
    }

    /// Sets the maximum number of concurrent sessions.
    pub fn with_max_sessions(mut self, max: usize) -> Self {
        self.max_sessions = max;
        self
    }

    /// Validates the configuration for internal consistency.
    ///
    /// Returns an error if any parameter is out of range or contradictory.
    pub fn validate(&self) -> Result<(), CoreError> {
        if self.max_loaded_nodes == 0 {
            return Err(CoreError::Validation(
                "max_loaded_nodes must be at least 1".to_string(),
            ));
        }
        if self.memory_budget_bytes == 0 {
            return Err(CoreError::Validation(
                "memory_budget_bytes must be greater than 0".to_string(),
            ));
        }
        if self.max_sessions == 0 {
            return Err(CoreError::Validation(
                "max_sessions must be at least 1".to_string(),
            ));
        }
        if let Err(e) = self.default_retry_policy.validate() {
            return Err(CoreError::Validation(format!(
                "invalid default_retry_policy: {}",
                e
            )));
        }
        Ok(())
    }
}

impl Default for OrchestratorConfig {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_is_valid() {
        let config = OrchestratorConfig::default();
        assert!(config.validate().is_ok());
        assert_eq!(config.max_loaded_nodes, DEFAULT_MAX_LOADED_NODES);
        assert_eq!(config.memory_budget_bytes, DEFAULT_MEMORY_BUDGET_BYTES);
        assert_eq!(config.max_sessions, DEFAULT_MAX_SESSIONS);
    }

    #[test]
    fn with_memory_limits() {
        let config = OrchestratorConfig::with_memory_limits(10, 1024 * 1024);
        assert!(config.validate().is_ok());
        assert_eq!(config.max_loaded_nodes, 10);
        assert_eq!(config.memory_budget_bytes, 1024 * 1024);
    }

    #[test]
    fn with_retry_policy() {
        let policy = RetryPolicy::no_retry();
        let config = OrchestratorConfig::default().with_retry_policy(policy.clone());
        assert_eq!(config.default_retry_policy, policy);
    }

    #[test]
    fn with_max_sessions() {
        let config = OrchestratorConfig::default().with_max_sessions(50);
        assert_eq!(config.max_sessions, 50);
    }

    #[test]
    fn validate_zero_max_loaded_nodes() {
        let config = OrchestratorConfig {
            max_loaded_nodes: 0,
            ..OrchestratorConfig::default()
        };
        assert!(config.validate().is_err());
    }

    #[test]
    fn validate_zero_memory_budget() {
        let config = OrchestratorConfig {
            memory_budget_bytes: 0,
            ..OrchestratorConfig::default()
        };
        assert!(config.validate().is_err());
    }

    #[test]
    fn validate_zero_max_sessions() {
        let config = OrchestratorConfig {
            max_sessions: 0,
            ..OrchestratorConfig::default()
        };
        assert!(config.validate().is_err());
    }
}
