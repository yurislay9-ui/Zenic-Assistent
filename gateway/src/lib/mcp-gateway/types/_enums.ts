// ─── Zenic-Agents v3 — MCP Gateway Type System ──────────────────────
// Enum-like Constants for the MCP Gateway

/** Tool risk levels — determines approval requirements */
export const RiskLevel = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
} as const;
export type RiskLevel = (typeof RiskLevel)[keyof typeof RiskLevel];

/** Tool statuses */
export const ToolStatus = {
  ACTIVE: "active",
  DEPRECATED: "deprecated",
  DISABLED: "disabled",
  TESTING: "testing",
} as const;
export type ToolStatus = (typeof ToolStatus)[keyof typeof ToolStatus];

/** Tool categories */
export const ToolCategory = {
  DATA: "data",
  COMMUNICATION: "communication",
  COMPUTE: "compute",
  STORAGE: "storage",
  EXTERNAL: "external",
  SECURITY: "security",
  MONITORING: "monitoring",
} as const;
export type ToolCategory = (typeof ToolCategory)[keyof typeof ToolCategory];

/** Server statuses */
export const ServerStatus = {
  ACTIVE: "active",
  UNHEALTHY: "unhealthy",
  OFFLINE: "offline",
  MAINTENANCE: "maintenance",
} as const;
export type ServerStatus = (typeof ServerStatus)[keyof typeof ServerStatus];

/** Server protocols */
export const ServerProtocol = {
  HTTP: "http",
  WEBSOCKET: "websocket",
  GRPC: "grpc",
  STDIO: "stdio",
} as const;
export type ServerProtocol = (typeof ServerProtocol)[keyof typeof ServerProtocol];

/** Execution statuses — full lifecycle */
export const ExecStatus = {
  PENDING: "pending",
  APPROVED: "approved",
  RUNNING: "running",
  COMPLETED: "completed",
  FAILED: "failed",
  DENIED: "denied",
  TIMEOUT: "timeout",
} as const;
export type ExecStatus = (typeof ExecStatus)[keyof typeof ExecStatus];

/** Gateway verdicts — the core arbitration */
export const Verdict = {
  ALLOW: "allow",
  DENY: "deny",
  CONDITIONAL: "conditional",
} as const;
export type Verdict = (typeof Verdict)[keyof typeof Verdict];

/** Audit severity levels */
export const AuditSeverity = {
  DEBUG: "debug",
  INFO: "info",
  WARN: "warn",
  ERROR: "error",
  CRITICAL: "critical",
} as const;
export type AuditSeverity = (typeof AuditSeverity)[keyof typeof AuditSeverity];

/** Audit outcomes */
export const AuditOutcome = {
  SUCCESS: "success",
  FAILURE: "failure",
  DENIED: "denied",
  ERROR: "error",
} as const;
export type AuditOutcome = (typeof AuditOutcome)[keyof typeof AuditOutcome];

/** Actor types */
export const ActorType = {
  USER: "user",
  SYSTEM: "system",
  SERVICE: "service",
  AGENT: "agent",
} as const;
export type ActorType = (typeof ActorType)[keyof typeof ActorType];

/** Policy types */
export const PolicyType = {
  ALLOW: "allow",
  DENY: "deny",
  CONDITIONAL: "conditional",
  QUOTA: "quota",
} as const;
export type PolicyType = (typeof PolicyType)[keyof typeof PolicyType];

/** Policy effects */
export const PolicyEffect = {
  ALLOW: "allow",
  DENY: "deny",
  REQUIRE_APPROVAL: "require_approval",
} as const;
export type PolicyEffect = (typeof PolicyEffect)[keyof typeof PolicyEffect];

/** User statuses */
export const UserStatus = {
  ACTIVE: "active",
  SUSPENDED: "suspended",
  DEACTIVATED: "deactivated",
} as const;
export type UserStatus = (typeof UserStatus)[keyof typeof UserStatus];

/** Auth types for MCP servers */
export const AuthType = {
  NONE: "none",
  API_KEY: "api_key",
  OAUTH2: "oauth2",
  MTLS: "mtls",
} as const;
export type AuthType = (typeof AuthType)[keyof typeof AuthType];
