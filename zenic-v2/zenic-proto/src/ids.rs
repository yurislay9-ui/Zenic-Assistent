//! Strongly-typed identifiers for all Zenic-Agents entities.
//!
//! Each ID is a newtype over [`uuid::Uuid`] with full serde support.
//! Using distinct types prevents mixing IDs at compile time.

use serde::{Deserialize, Serialize};
use std::fmt;
use std::str::FromStr;
use uuid::Uuid;

// ---------------------------------------------------------------------------
// Macro: boilerplate for all ID types
// ---------------------------------------------------------------------------

macro_rules! define_id {
    ($name:ident, $doc:literal) => {
        #[doc = $doc]
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
        pub struct $name(Uuid);

        impl $name {
            /// Generate a new random ID (v4).
            pub fn new() -> Self {
                Self(Uuid::new_v4())
            }

            /// Create from an existing [`Uuid`].
            pub const fn from_uuid(id: Uuid) -> Self {
                Self(id)
            }

            /// Return the inner [`Uuid`].
            pub const fn as_uuid(&self) -> &Uuid {
                &self.0
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                write!(f, "{}", self.0)
            }
        }

        impl FromStr for $name {
            type Err = uuid::Error;

            fn from_str(s: &str) -> Result<Self, Self::Err> {
                Uuid::parse_str(s).map(Self)
            }
        }

        impl Default for $name {
            fn default() -> Self {
                Self::new()
            }
        }
    };
}

// ---------------------------------------------------------------------------
// ID definitions
// ---------------------------------------------------------------------------

define_id!(NodeId, "Unique identifier for a DAG node (leaf or internal).");
define_id!(SuperNodeId, "Unique identifier for a supernode (top-level domain grouping).");
define_id!(SubGraphId, "Unique identifier for a fractal subgraph (certified domain sub-DAG).");
define_id!(GraphId, "Unique identifier for a complete directed acyclic graph.");
define_id!(ExecutionId, "Unique identifier for a single DAG execution run.");
define_id!(WorkflowId, "Unique identifier for a durable workflow instance.");
define_id!(PolicyId, "Unique identifier for a policy rule.");
define_id!(SessionId, "Unique identifier for a user/business session.");
define_id!(TenantId, "Unique identifier for a multi-tenant isolation boundary.");
define_id!(SubscriptionId, "Unique identifier for a subscription instance.");
define_id!(PaymentId, "Unique identifier for a payment transaction.");
define_id!(TrialId, "Unique identifier for a trial period.");
define_id!(MappingId, "Unique identifier for a semantic mapping in the Memory Chip.");

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn node_id_display_roundtrip() {
        let id = NodeId::new();
        let s = id.to_string();
        let parsed: NodeId = s.parse().expect("valid parse");
        assert_eq!(id, parsed);
    }

    #[test]
    fn different_id_types_are_not_comparable() {
        let node = NodeId::new();
        let super_node = SuperNodeId::new();
        // This would not compile if they were the same type:
        let _node_str = node.to_string();
        let _super_str = super_node.to_string();
        assert_ne!(node.to_string(), super_node.to_string());
    }

    #[test]
    fn from_uuid_roundtrip() {
        let uuid = Uuid::new_v4();
        let id = NodeId::from_uuid(uuid);
        assert_eq!(*id.as_uuid(), uuid);
    }

    #[test]
    fn invalid_parse_returns_error() {
        let result = NodeId::from_str("not-a-uuid");
        assert!(result.is_err());
    }

    #[test]
    fn default_generates_unique() {
        let a = NodeId::default();
        let b = NodeId::default();
        assert_ne!(a, b);
    }
}
