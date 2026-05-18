// ─── Zenic-Agents v3 — MCP Gateway Type System ──────────────────────
// DTO and API Response Types

import type {
  RiskLevel,
  ToolCategory,
  ToolStatus,
  ServerProtocol,
  ServerStatus,
  AuthType,
  AuditSeverity,
  AuditOutcome,
  PolicyType,
  PolicyEffect,
} from "./_enums";

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
  verdict: import("./_enums").Verdict;
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
  field: string;
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

/** API Response wrapper */
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
}

/** Paginated API Response */
export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

/** API Error */
export interface ApiError {
  success: false;
  error: string;
  code: string;
  details?: unknown;
}
