//! Policy context types for evaluation requests.

use zenic_proto::{BusinessDomain, NodeCriticality, NodeId, SessionId, TenantId};

use crate::permission::Permission;

// ---------------------------------------------------------------------------
// PolicyContext
// ---------------------------------------------------------------------------

/// Context for a single policy evaluation request.
///
/// Contains all the information needed to make an access decision:
/// who is requesting, what they want to do, and optional context
/// about the target (domain, criticality).
pub struct PolicyContext {
    /// The session making the request.
    pub session_id: SessionId,
    /// The tenant within which the request is made.
    pub tenant_id: TenantId,
    /// The permission being requested.
    pub permission: Permission,
    /// Optional business domain of the target resource.
    pub domain: Option<BusinessDomain>,
    /// Optional criticality of the target node (for gate checks).
    pub criticality: Option<NodeCriticality>,
    /// Optional node ID for the target (for gate checks).
    pub node_id: Option<NodeId>,
}

impl PolicyContext {
    /// Creates a basic policy context with just session, tenant, and permission.
    pub fn new(
        session_id: SessionId,
        tenant_id: TenantId,
        permission: Permission,
    ) -> Self {
        Self {
            session_id,
            tenant_id,
            permission,
            domain: None,
            criticality: None,
            node_id: None,
        }
    }

    /// Adds domain context to the policy request.
    pub fn with_domain(mut self, domain: BusinessDomain) -> Self {
        self.domain = Some(domain);
        self
    }

    /// Adds criticality context for gate checks.
    pub fn with_criticality(mut self, criticality: NodeCriticality, node_id: NodeId) -> Self {
        self.criticality = Some(criticality);
        self.node_id = Some(node_id);
        self
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::permission::{Action, Resource};

    #[test]
    fn policy_context_new() {
        let ctx = PolicyContext::new(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Execute, Resource::AllNodes),
        );
        assert!(ctx.domain.is_none());
        assert!(ctx.criticality.is_none());
        assert!(ctx.node_id.is_none());
    }

    #[test]
    fn policy_context_with_domain() {
        let ctx = PolicyContext::new(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Execute, Resource::AllNodes),
        )
        .with_domain(BusinessDomain::ECommerce);
        assert_eq!(ctx.domain, Some(BusinessDomain::ECommerce));
    }

    #[test]
    fn policy_context_with_criticality() {
        let node_id = NodeId::new();
        let ctx = PolicyContext::new(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Execute, Resource::AllNodes),
        )
        .with_criticality(NodeCriticality::High, node_id);
        assert_eq!(ctx.criticality, Some(NodeCriticality::High));
        assert_eq!(ctx.node_id, Some(node_id));
    }
}
