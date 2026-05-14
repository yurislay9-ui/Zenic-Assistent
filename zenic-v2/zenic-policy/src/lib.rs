//! # zenic-policy
//!
//! Policy engine with RBAC, safety veto (immutable), and criticality gates
//! for Zenic-Agents.
//!
//! This crate provides:
//! - [`Permission`] / [`Action`] / [`Resource`] — access control primitives
//! - [`Role`] / [`RoleRegistry`] / [`RoleAssignment`] — RBAC role management
//! - [`PolicyRule`] / [`RuleSet`] / [`RuleCondition`] — explicit allow/deny rules
//! - [`SafetyVeto`] / [`SafetyVetoRegistry`] — immutable deny rules
//! - [`CriticalityGate`] — node criticality clearance enforcement
//! - [`PolicyEngine`] — main evaluation engine
//! - [`AuditLog`] / [`AuditEntry`] — decision audit trail

pub mod audit;
pub mod engine;
pub mod errors;
pub mod gate;
pub mod permission;
pub mod role;
pub mod rule;

// Convenience re-exports.
pub use audit::{AuditEntry, AuditLog, DenialReason, PolicyDecision};
pub use engine::{PolicyContext, PolicyEngine};
pub use errors::PolicyError;
pub use gate::{CriticalityGate, SafetyVeto, SafetyVetoRegistry};
pub use permission::{Action, Permission, Resource};
pub use role::{
    CriticalityClearance, Role, RoleAssignment, RoleId, RolePriority, RoleRegistry,
};
pub use rule::{PolicyRule, RuleCondition, RuleEffect, RuleSet};
