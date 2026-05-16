// ─── Zenic-Agents v3 — MCP Gateway Type System ──────────────────────
// Phase 1: Complete TypeScript types, constants, and enums
// Philosophy: "IA never generates, only arbitrates YES/NO"

// ─── Enum-like Constants ────────────────────────────────────────────

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

// ─── Risk Level Config ──────────────────────────────────────────────

export const RISK_LEVEL_CONFIG: Record<RiskLevel, {
  label: string;
  color: string;
  bgColor: string;
  requiresApproval: boolean;
  maxRetries: number;
}> = {
  low: { label: "Low", color: "text-green-700 dark:text-green-400", bgColor: "bg-green-100 dark:bg-green-900/30", requiresApproval: false, maxRetries: 3 },
  medium: { label: "Medium", color: "text-yellow-700 dark:text-yellow-400", bgColor: "bg-yellow-100 dark:bg-yellow-900/30", requiresApproval: false, maxRetries: 2 },
  high: { label: "High", color: "text-orange-700 dark:text-orange-400", bgColor: "bg-orange-100 dark:bg-orange-900/30", requiresApproval: true, maxRetries: 1 },
  critical: { label: "Critical", color: "text-red-700 dark:text-red-400", bgColor: "bg-red-100 dark:bg-red-900/30", requiresApproval: true, maxRetries: 0 },
};

export const EXEC_STATUS_CONFIG: Record<ExecStatus, {
  label: string;
  color: string;
  bgColor: string;
}> = {
  pending: { label: "Pending", color: "text-gray-700 dark:text-gray-300", bgColor: "bg-gray-100 dark:bg-gray-800" },
  approved: { label: "Approved", color: "text-blue-700 dark:text-blue-400", bgColor: "bg-blue-100 dark:bg-blue-900/30" },
  running: { label: "Running", color: "text-cyan-700 dark:text-cyan-400", bgColor: "bg-cyan-100 dark:bg-cyan-900/30" },
  completed: { label: "Completed", color: "text-green-700 dark:text-green-400", bgColor: "bg-green-100 dark:bg-green-900/30" },
  failed: { label: "Failed", color: "text-red-700 dark:text-red-400", bgColor: "bg-red-100 dark:bg-red-900/30" },
  denied: { label: "Denied", color: "text-rose-700 dark:text-rose-400", bgColor: "bg-rose-100 dark:bg-rose-900/30" },
  timeout: { label: "Timeout", color: "text-amber-700 dark:text-amber-400", bgColor: "bg-amber-100 dark:bg-amber-900/30" },
};

export const SEVERITY_CONFIG: Record<AuditSeverity, {
  label: string;
  color: string;
  bgColor: string;
  icon: string;
}> = {
  debug: { label: "Debug", color: "text-gray-500", bgColor: "bg-gray-50", icon: "Bug" },
  info: { label: "Info", color: "text-blue-600", bgColor: "bg-blue-50", icon: "Info" },
  warn: { label: "Warning", color: "text-yellow-600", bgColor: "bg-yellow-50", icon: "AlertTriangle" },
  error: { label: "Error", color: "text-red-600", bgColor: "bg-red-50", icon: "XCircle" },
  critical: { label: "Critical", color: "text-red-800", bgColor: "bg-red-100", icon: "ShieldAlert" },
};

export const TOOL_CATEGORY_CONFIG: Record<ToolCategory, {
  label: string;
  icon: string;
  color: string;
}> = {
  data: { label: "Data", icon: "Database", color: "text-violet-600" },
  communication: { label: "Communication", icon: "MessageSquare", color: "text-sky-600" },
  compute: { label: "Compute", icon: "Cpu", color: "text-orange-600" },
  storage: { label: "Storage", icon: "HardDrive", color: "text-emerald-600" },
  external: { label: "External", icon: "Globe", color: "text-pink-600" },
  security: { label: "Security", icon: "Shield", color: "text-red-600" },
  monitoring: { label: "Monitoring", icon: "Activity", color: "text-cyan-600" },
};

// ─── DTO Types ──────────────────────────────────────────────────────

/** Create/Update Tool DTO */
export interface ToolDTO {
  id?: string;
  name: string;
  displayName: string;
  description: string;
  category: ToolCategory;
  version: string;
  icon?: string;
  endpoint: string;
  method: string;
  inputSchema: string;
  outputSchema?: string;
  timeout: number;
  retries: number;
  rateLimit: number;
  riskLevel: RiskLevel;
  status: ToolStatus;
  requiresApproval: boolean;
  tags: string[];
  metadata: Record<string, unknown>;
  serverId?: string;
}

/** Create/Update Server DTO */
export interface ServerDTO {
  id?: string;
  name: string;
  displayName: string;
  description: string;
  url: string;
  protocol: ServerProtocol;
  status: ServerStatus;
  healthCheckUrl?: string;
  authType: AuthType;
  authConfig: Record<string, unknown>;
  capabilities: string[];
  metadata: Record<string, unknown>;
}

/** Gateway Execution Request */
export interface ExecutionRequest {
  toolName: string;
  input: Record<string, unknown>;
  executorId?: string;
  correlationId?: string;
  bypassApproval?: boolean;
}

/** Gateway Verdict Response */
export interface VerdictResponse {
  verdict: Verdict;
  reason: string;
  executionId?: string;
  requiresApproval: boolean;
  conditions?: string[];
  quotaRemaining?: number;
}

/** RBAC Permission Check */
export interface PermissionCheck {
  userId: string;
  resource: string;
  action: string;
  context?: Record<string, unknown>;
}

/** RBAC Check Result */
export interface PermissionCheckResult {
  allowed: boolean;
  reason: string;
  matchedPolicies: string[];
  constraints?: Record<string, unknown>;
  expiresAt?: string;
}

/** Role DTO */
export interface RoleDTO {
  id?: string;
  name: string;
  displayName: string;
  description: string;
  color: string;
  isSystem: boolean;
  priority: number;
  permissionIds: string[];
}

/** Policy Condition */
export interface PolicyCondition {
  field: string;        // e.g. "riskLevel", "timeOfDay", "executorRole"
  operator: "eq" | "neq" | "in" | "notin" | "gt" | "lt" | "gte" | "lte" | "regex";
  value: unknown;
}

/** Policy DTO */
export interface PolicyDTO {
  id?: string;
  name: string;
  description: string;
  type: PolicyType;
  priority: number;
  isEnabled: boolean;
  conditions: PolicyCondition[];
  effect: PolicyEffect;
  timeWindow?: { start: string; end: string; tz: string };
  quota?: { maxCalls: number; window: string };
  toolIds: string[];
}

/** Audit Log Query */
export interface AuditQuery {
  actorId?: string;
  action?: string;
  resource?: string;
  severity?: AuditSeverity;
  outcome?: AuditOutcome;
  startDate?: string;
  endDate?: string;
  search?: string;
  page?: number;
  pageSize?: number;
}

/** Dashboard Metrics */
export interface DashboardMetrics {
  totalTools: number;
  activeTools: number;
  totalServers: number;
  healthyServers: number;
  executionsToday: number;
  executionsSuccessRate: number;
  avgExecutionTime: number;
  deniedExecutions: number;
  pendingApprovals: number;
  criticalAlerts: number;
  topTools: Array<{ name: string; count: number; successRate: number }>;
  executionsByHour: Array<{ hour: string; count: number; failures: number }>;
  riskDistribution: Record<RiskLevel, number>;
  categoryDistribution: Record<ToolCategory, number>;
}

/** Activity feed item */
export interface ActivityItem {
  id: string;
  type: "execution" | "approval" | "policy_change" | "role_change" | "alert";
  title: string;
  description: string;
  timestamp: string;
  severity: AuditSeverity;
  actorName?: string;
  resourceName?: string;
}

// ─── API Response Types ─────────────────────────────────────────────

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface ApiError {
  success: false;
  error: string;
  code: string;
  details?: unknown;
}

// ─── Resource Action Constants ──────────────────────────────────────

export const RESOURCES = {
  TOOL: "tool",
  SERVER: "server",
  ROLE: "role",
  PERMISSION: "permission",
  POLICY: "policy",
  AUDIT: "audit",
  DASHBOARD: "dashboard",
  EXECUTION: "execution",
  USER: "user",
} as const;

export const ACTIONS = {
  READ: "read",
  WRITE: "write",
  DELETE: "delete",
  EXECUTE: "execute",
  ADMIN: "admin",
  APPROVE: "approve",
  EXPORT: "export",
} as const;

/** Default system permissions to seed */
export const DEFAULT_PERMISSIONS: Array<{
  name: string;
  resource: string;
  action: string;
  displayName: string;
  description: string;
  isDangerous: boolean;
}> = [
  { name: "tool:read", resource: "tool", action: "read", displayName: "Read Tools", description: "View tool registry and details", isDangerous: false },
  { name: "tool:write", resource: "tool", action: "write", displayName: "Manage Tools", description: "Create, update, and configure tools", isDangerous: false },
  { name: "tool:execute", resource: "tool", action: "execute", displayName: "Execute Tools", description: "Run tool executions through gateway", isDangerous: true },
  { name: "tool:delete", resource: "tool", action: "delete", displayName: "Delete Tools", description: "Remove tools from registry", isDangerous: true },
  { name: "server:read", resource: "server", action: "read", displayName: "Read Servers", description: "View MCP server configurations", isDangerous: false },
  { name: "server:write", resource: "server", action: "write", displayName: "Manage Servers", description: "Configure MCP servers", isDangerous: false },
  { name: "role:read", resource: "role", action: "read", displayName: "Read Roles", description: "View role configurations", isDangerous: false },
  { name: "role:write", resource: "role", action: "write", displayName: "Manage Roles", description: "Create and modify roles", isDangerous: true },
  { name: "role:delete", resource: "role", action: "delete", displayName: "Delete Roles", description: "Remove roles from system", isDangerous: true },
  { name: "policy:read", resource: "policy", action: "read", displayName: "Read Policies", description: "View access policies", isDangerous: false },
  { name: "policy:write", resource: "policy", action: "write", displayName: "Manage Policies", description: "Create and modify access policies", isDangerous: true },
  { name: "policy:delete", resource: "policy", action: "delete", displayName: "Delete Policies", description: "Remove access policies", isDangerous: true },
  { name: "audit:read", resource: "audit", action: "read", displayName: "Read Audit Logs", description: "View audit trail", isDangerous: false },
  { name: "audit:export", resource: "audit", action: "export", displayName: "Export Audit Logs", description: "Export audit data", isDangerous: true },
  { name: "execution:read", resource: "execution", action: "read", displayName: "Read Executions", description: "View execution history", isDangerous: false },
  { name: "execution:approve", resource: "execution", action: "approve", displayName: "Approve Executions", description: "Approve pending tool executions", isDangerous: true },
  { name: "dashboard:read", resource: "dashboard", action: "read", displayName: "View Dashboard", description: "Access dashboard metrics", isDangerous: false },
  { name: "user:admin", resource: "user", action: "admin", displayName: "Admin Users", description: "Full user management", isDangerous: true },
];

/** Default system roles */
export const DEFAULT_ROLES: Array<{
  name: string;
  displayName: string;
  description: string;
  color: string;
  isSystem: boolean;
  priority: number;
  permissionNames: string[];
}> = [
  {
    name: "superadmin",
    displayName: "Super Admin",
    description: "Full system access — no restrictions",
    color: "#dc2626",
    isSystem: true,
    priority: 100,
    permissionNames: ["tool:read", "tool:write", "tool:execute", "tool:delete", "server:read", "server:write", "role:read", "role:write", "role:delete", "policy:read", "policy:write", "policy:delete", "audit:read", "audit:export", "execution:read", "execution:approve", "dashboard:read", "user:admin"],
  },
  {
    name: "admin",
    displayName: "Admin",
    description: "Manage tools, policies, and roles",
    color: "#ea580c",
    isSystem: true,
    priority: 80,
    permissionNames: ["tool:read", "tool:write", "tool:execute", "tool:delete", "server:read", "server:write", "role:read", "policy:read", "policy:write", "audit:read", "execution:read", "execution:approve", "dashboard:read"],
  },
  {
    name: "operator",
    displayName: "Operator",
    description: "Execute tools and monitor system",
    color: "#0891b2",
    isSystem: true,
    priority: 50,
    permissionNames: ["tool:read", "tool:execute", "server:read", "policy:read", "audit:read", "execution:read", "dashboard:read"],
  },
  {
    name: "viewer",
    displayName: "Viewer",
    description: "Read-only access to tools and audit logs",
    color: "#6b7280",
    isSystem: true,
    priority: 10,
    permissionNames: ["tool:read", "server:read", "audit:read", "dashboard:read"],
  },
];
