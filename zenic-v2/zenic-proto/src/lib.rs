//! # zenic-proto
//!
//! Shared types, IDs, domain enums, and serialization for Zenic-Agents.
//!
//! This crate is the single source of truth for all cross-cutting types.
//! Every other crate in the workspace depends on `zenic-proto` and
//! **no other crate** redefines these types.

pub mod domain;
pub mod errors;
pub mod ids;
pub mod node_types;
pub mod serde_;

// Convenience re-exports: allow `zenic_proto::NodeId` instead of `zenic_proto::ids::NodeId`.
pub use domain::{BusinessDomain, DomainCapability};
pub use errors::ProtoError;
pub use ids::{ExecutionId, GraphId, NodeId, PolicyId, SessionId, SubGraphId, SuperNodeId, TenantId, WorkflowId};
pub use node_types::{LoadPolicy, NodeCategory, NodeCriticality};
pub use serde_::{decode, decode_raw, encode, encode_raw};
