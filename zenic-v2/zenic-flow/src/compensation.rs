//! SAGA compensation: trait and registry for compensating actions.
//!
//! When a workflow step fails, the SAGA pattern requires running
//! compensating actions for all previously completed steps in reverse
//! order. The [`CompensationAction`] trait defines how to compensate
//! a single step, and the [`CompensationRegistry`] maps step names
//! to their compensating actions.

use std::collections::HashMap;

use crate::errors::FlowError;
use crate::step::StepResult;

// ---------------------------------------------------------------------------
// CompensationAction trait
// ---------------------------------------------------------------------------

/// Trait for defining a compensating action for a workflow step.
///
/// Compensating actions are the "undo" operations in the SAGA pattern.
/// When a step fails, all previously completed steps that have a
/// compensating action are rolled back in reverse order.
///
/// Implementations must be `Send + Sync` so they can be shared
/// across thread boundaries if needed.
pub trait CompensationAction: Send + Sync {
    /// Executes the compensating action for a step.
    ///
    /// Receives the step's result (which includes output data from
    /// the original execution) and performs the rollback logic.
    ///
    /// Returns `Ok(())` if compensation succeeded, or an error
    /// describing what went wrong.
    fn compensate(&self, step_result: &StepResult) -> Result<(), FlowError>;

    /// Returns the human-readable name of this compensating action.
    fn name(&self) -> &str;
}

// ---------------------------------------------------------------------------
// CompensationRegistry
// ---------------------------------------------------------------------------

/// Registry that maps step names (or compensation keys) to their
/// compensating actions.
///
/// The registry is populated before workflow execution begins. During
/// SAGA rollback, the engine looks up each completed step's
/// `compensation_key` in this registry to find the action to run.
pub struct CompensationRegistry {
    actions: HashMap<String, Box<dyn CompensationAction>>,
}

impl CompensationRegistry {
    /// Creates an empty registry.
    pub fn new() -> Self {
        Self {
            actions: HashMap::new(),
        }
    }

    /// Registers a compensating action for a given key.
    ///
    /// Returns an error if an action is already registered for the key.
    pub fn register(
        &mut self,
        key: &str,
        action: Box<dyn CompensationAction>,
    ) -> Result<(), FlowError> {
        if key.is_empty() {
            return Err(FlowError::Validation(
                "compensation key must not be empty".to_string(),
            ));
        }
        if self.actions.contains_key(key) {
            return Err(FlowError::Validation(format!(
                "compensation action already registered for key '{}'",
                key
            )));
        }
        self.actions.insert(key.to_string(), action);
        Ok(())
    }

    /// Returns the compensating action for a key, if registered.
    pub fn get(&self, key: &str) -> Option<&dyn CompensationAction> {
        self.actions.get(key).map(|a| a.as_ref())
    }

    /// Whether a compensating action is registered for the given key.
    pub fn contains(&self, key: &str) -> bool {
        self.actions.contains_key(key)
    }

    /// Returns the number of registered compensating actions.
    pub fn len(&self) -> usize {
        self.actions.len()
    }

    /// Whether the registry is empty.
    pub fn is_empty(&self) -> bool {
        self.actions.is_empty()
    }

    /// Runs all compensating actions for the given completed steps
    /// in reverse order (SAGA pattern).
    ///
    /// Steps without a `compensation_key` or without a registered
    /// action are skipped. If a compensation fails, the error is
    /// recorded but the remaining steps are still compensated
    /// (best-effort compensation).
    ///
    /// Returns a list of errors encountered during compensation.
    /// An empty list means all compensations succeeded.
    pub fn compensate_steps(
        &self,
        step_results: &[StepResult],
        compensation_keys: &[Option<String>],
    ) -> Vec<FlowError> {
        let mut errors = Vec::new();

        // Iterate in reverse order over completed steps.
        for i in (0..step_results.len()).rev() {
            let result = &step_results[i];

            // Only compensate completed steps.
            if !result.is_success() {
                continue;
            }

            // Look up the compensation key for this step.
            let key = match compensation_keys.get(i).and_then(|k| k.as_ref()) {
                Some(k) => k,
                None => continue,
            };

            // Look up the action.
            let action = match self.actions.get(key) {
                Some(a) => a,
                None => continue,
            };

            // Execute compensation.
            if let Err(e) = action.compensate(result) {
                errors.push(FlowError::CompensationFailed {
                    step_index: i,
                    message: format!("compensation '{}' failed: {}", action.name(), e),
                });
            }
        }

        errors
    }
}

impl Default for CompensationRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Built-in: NoOpCompensation
// ---------------------------------------------------------------------------

/// A no-op compensation action that does nothing.
///
/// Useful as a placeholder when a step needs a compensation key
/// but the compensation logic is not yet implemented.
pub struct NoOpCompensation {
    name: String,
}

impl NoOpCompensation {
    /// Creates a new no-op compensation with a descriptive name.
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
        }
    }
}

impl CompensationAction for NoOpCompensation {
    fn compensate(&self, _step_result: &StepResult) -> Result<(), FlowError> {
        Ok(())
    }

    fn name(&self) -> &str {
        &self.name
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // Helper: a compensation action that tracks whether it was called.
    // Uses Arc<AtomicBool> so the flag can be observed after the action
    // is moved into the registry.
    struct TrackingCompensation {
        name: String,
        called: std::sync::Arc<std::sync::atomic::AtomicBool>,
    }

    impl TrackingCompensation {
        fn new(name: &str) -> (Self, std::sync::Arc<std::sync::atomic::AtomicBool>) {
            let flag = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
            let action = Self {
                name: name.to_string(),
                called: flag.clone(),
            };
            (action, flag)
        }
    }

    impl CompensationAction for TrackingCompensation {
        fn compensate(&self, _step_result: &StepResult) -> Result<(), FlowError> {
            self.called.store(true, std::sync::atomic::Ordering::SeqCst);
            Ok(())
        }

        fn name(&self) -> &str {
            &self.name
        }
    }

    // Helper: a compensation action that always fails.
    struct FailingCompensation {
        name: String,
    }

    impl FailingCompensation {
        fn new(name: &str) -> Self {
            Self {
                name: name.to_string(),
            }
        }
    }

    impl CompensationAction for FailingCompensation {
        fn compensate(&self, _step_result: &StepResult) -> Result<(), FlowError> {
            Err(FlowError::General("intentional failure".to_string()))
        }

        fn name(&self) -> &str {
            &self.name
        }
    }

    #[test]
    fn registry_register_and_get() {
        let mut reg = CompensationRegistry::new();
        reg.register("cancel_order", Box::new(NoOpCompensation::new("cancel_order")))
            .expect("register");
        assert_eq!(reg.len(), 1);
        assert!(reg.contains("cancel_order"));
        assert!(!reg.contains("unknown"));
    }

    #[test]
    fn registry_duplicate_key_fails() {
        let mut reg = CompensationRegistry::new();
        reg.register("key", Box::new(NoOpCompensation::new("key")))
            .expect("register");
        let result = reg.register("key", Box::new(NoOpCompensation::new("key2")));
        assert!(result.is_err());
    }

    #[test]
    fn registry_empty_key_fails() {
        let mut reg = CompensationRegistry::new();
        let result = reg.register("", Box::new(NoOpCompensation::new("empty")));
        assert!(result.is_err());
    }

    #[test]
    fn registry_default_is_new() {
        let reg = CompensationRegistry::default();
        assert!(reg.is_empty());
    }

    #[test]
    fn noop_compensation_succeeds() {
        let action = NoOpCompensation::new("test");
        let result = StepResult::completed("step".to_string(), 0, vec![], 1, 10);
        assert!(action.compensate(&result).is_ok());
        assert_eq!(action.name(), "test");
    }

    #[test]
    fn compensate_steps_in_reverse_order() {
        let (action0, flag0) = TrackingCompensation::new("comp_0");
        let (action1, flag1) = TrackingCompensation::new("comp_1");

        let mut reg = CompensationRegistry::new();
        reg.register("comp_0", Box::new(action0)).expect("register");
        reg.register("comp_1", Box::new(action1)).expect("register");

        let results = vec![
            StepResult::completed("step0".to_string(), 0, vec![], 1, 10),
            StepResult::completed("step1".to_string(), 1, vec![], 1, 10),
        ];
        let keys = vec![
            Some("comp_0".to_string()),
            Some("comp_1".to_string()),
        ];

        let errors = reg.compensate_steps(&results, &keys);
        assert!(errors.is_empty());
        assert!(flag0.load(std::sync::atomic::Ordering::SeqCst));
        assert!(flag1.load(std::sync::atomic::Ordering::SeqCst));
    }

    #[test]
    fn compensate_steps_skips_without_key() {
        let mut reg = CompensationRegistry::new();
        reg.register("comp_1", Box::new(NoOpCompensation::new("comp_1")))
            .expect("register");

        let results = vec![
            StepResult::completed("step0".to_string(), 0, vec![], 1, 10),
            StepResult::completed("step1".to_string(), 1, vec![], 1, 10),
        ];
        let keys: Vec<Option<String>> = vec![None, Some("comp_1".to_string())];

        let errors = reg.compensate_steps(&results, &keys);
        assert!(errors.is_empty());
    }

    #[test]
    fn compensate_steps_best_effort_on_failure() {
        let mut reg = CompensationRegistry::new();
        reg.register("fail", Box::new(FailingCompensation::new("fail")))
            .expect("register");
        reg.register("ok", Box::new(NoOpCompensation::new("ok")))
            .expect("register");

        let results = vec![
            StepResult::completed("step0".to_string(), 0, vec![], 1, 10),
            StepResult::completed("step1".to_string(), 1, vec![], 1, 10),
        ];
        let keys = vec![
            Some("ok".to_string()),
            Some("fail".to_string()),
        ];

        let errors = reg.compensate_steps(&results, &keys);
        assert_eq!(errors.len(), 1);
        assert!(matches!(errors[0], FlowError::CompensationFailed { step_index: 1, .. }));
    }

    #[test]
    fn compensate_steps_skips_non_completed() {
        let mut reg = CompensationRegistry::new();
        reg.register("comp", Box::new(NoOpCompensation::new("comp")))
            .expect("register");

        let results = vec![
            StepResult::completed("step0".to_string(), 0, vec![], 1, 10),
            StepResult::failed("step1".to_string(), 1, 1, "error".to_string(), 10),
            StepResult::skipped("step2".to_string(), 2),
        ];
        let keys = vec![
            Some("comp".to_string()),
            Some("comp".to_string()),
            Some("comp".to_string()),
        ];

        let errors = reg.compensate_steps(&results, &keys);
        assert!(errors.is_empty()); // Only step0 was completed and compensated.
    }
}
