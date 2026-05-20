//! Audit module tests.

#[cfg(test)]
mod tests {
    use super::super::types::{AuditEntry, AuditLog, DenialReason, PolicyDecision};
    use crate::permission::{Action, Resource};
    use zenic_proto::{NodeId, RoleId, SessionId, TenantId};

    #[test]
    fn policy_decision_display() {
        assert_eq!(PolicyDecision::Allowed.to_string(), "allowed");
        assert_eq!(PolicyDecision::Denied.to_string(), "denied");
    }

    #[test]
    fn denial_reason_display() {
        assert_eq!(DenialReason::NoMatchingRole.to_string(), "no_matching_role");
        assert_eq!(
            DenialReason::RuleDenied("no_delete".to_string()).to_string(),
            "rule_denied:no_delete"
        );
        assert_eq!(
            DenialReason::SafetyVeto("veto1".to_string()).to_string(),
            "safety_veto:veto1"
        );
        assert_eq!(DenialReason::CriticalityGate.to_string(), "criticality_gate");
        assert_eq!(DenialReason::DefaultDeny.to_string(), "default_deny");
    }

    #[test]
    fn audit_entry_allowed() {
        let entry = AuditEntry::allowed(
            1000,
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Execute, Resource::AllNodes),
            vec![RoleId::new()],
        );
        assert!(entry.is_allowance());
        assert!(!entry.is_denial());
        assert!(entry.denial_reason.is_none());
    }

    #[test]
    fn audit_entry_denied() {
        let entry = AuditEntry::denied(
            2000,
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Delete, Resource::Node(NodeId::new())),
            DenialReason::SafetyVeto("no_delete".to_string()),
            vec![],
        );
        assert!(entry.is_denial());
        assert!(!entry.is_allowance());
        assert!(entry.denial_reason.is_some());
    }

    #[test]
    fn audit_log_record_allowed() {
        let mut log = AuditLog::new();
        log.record_allowed(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Execute, Resource::AllNodes),
            vec![RoleId::new()],
        );
        assert_eq!(log.len(), 1);
        assert!(log.entries()[0].is_allowance());
    }

    #[test]
    fn audit_log_record_denied() {
        let mut log = AuditLog::new();
        log.record_denied(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Delete, Resource::AllNodes),
            DenialReason::DefaultDeny,
            vec![],
        );
        assert_eq!(log.len(), 1);
        assert!(log.entries()[0].is_denial());
    }

    #[test]
    fn audit_log_denials_filter() {
        let mut log = AuditLog::new();
        log.record_allowed(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Execute, Resource::AllNodes),
            vec![],
        );
        log.record_denied(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Delete, Resource::AllNodes),
            DenialReason::DefaultDeny,
            vec![],
        );
        assert_eq!(log.denials().len(), 1);
        assert_eq!(log.allowances().len(), 1);
    }

    #[test]
    fn audit_log_entries_for_session() {
        let sid = SessionId::new();
        let tid = TenantId::new();
        let mut log = AuditLog::new();
        log.record_allowed(
            sid,
            tid,
            Permission::new(Action::Execute, Resource::AllNodes),
            vec![],
        );
        log.record_allowed(
            SessionId::new(), // Different session.
            tid,
            Permission::new(Action::Read, Resource::AllNodes),
            vec![],
        );
        assert_eq!(log.entries_for_session(&sid).len(), 1);
    }

    #[test]
    fn audit_log_entries_for_tenant() {
        let sid = SessionId::new();
        let tid1 = TenantId::new();
        let tid2 = TenantId::new();
        let mut log = AuditLog::new();
        log.record_allowed(
            sid,
            tid1,
            Permission::new(Action::Execute, Resource::AllNodes),
            vec![],
        );
        log.record_allowed(
            sid,
            tid2,
            Permission::new(Action::Read, Resource::AllNodes),
            vec![],
        );
        assert_eq!(log.entries_for_tenant(&tid1).len(), 1);
        assert_eq!(log.entries_for_tenant(&tid2).len(), 1);
    }

    #[test]
    fn audit_log_timestamps_monotonic() {
        let mut log = AuditLog::new();
        log.record_allowed(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Execute, Resource::AllNodes),
            vec![],
        );
        log.record_allowed(
            SessionId::new(),
            TenantId::new(),
            Permission::new(Action::Read, Resource::AllNodes),
            vec![],
        );
        let entries = log.entries();
        assert!(entries[0].timestamp_ms < entries[1].timestamp_ms);
    }

    #[test]
    fn audit_log_default_is_new() {
        let log = AuditLog::default();
        assert!(log.is_empty());
    }
}
