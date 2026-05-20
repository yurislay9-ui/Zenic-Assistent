//! Core types for policy rules: effect and condition enums.

use serde::{Deserialize, Serialize};
use std::fmt;
use zenic_proto::BusinessDomain;

use crate::permission::{Action, Resource};

// ---------------------------------------------------------------------------
// RuleEffect
// ---------------------------------------------------------------------------

/// The outcome of a policy rule when it matches.
///
/// Rules can either allow or deny an action. Deny rules take precedence
/// over allow rules in the policy engine (default-deny model).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RuleEffect {
    /// The action is explicitly allowed.
    Allow,
    /// The action is explicitly denied.
    Deny,
}

impl fmt::Display for RuleEffect {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Allow => write!(f, "allow"),
            Self::Deny => write!(f, "deny"),
        }
    }
}

// ---------------------------------------------------------------------------
// RuleCondition
// ---------------------------------------------------------------------------

/// A condition that must be true for a rule to apply.
///
/// Conditions are evaluated at runtime during policy evaluation.
/// A rule with no conditions always applies (unconditional rule).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RuleCondition {
    /// The action must target a node in the given business domain.
    DomainEquals(BusinessDomain),
    /// The action must target a specific resource (exact match).
    ResourceEquals(Resource),
    /// The action must be one of the specified actions.
    ActionIn(Vec<Action>),
    /// The action must target a resource of a specific type (wildcard).
    ResourceTypeEquals(String),
    /// A combination of conditions that must all be true.
    AllOf(Vec<RuleCondition>),
    /// A combination of conditions where at least one must be true.
    AnyOf(Vec<RuleCondition>),
}
