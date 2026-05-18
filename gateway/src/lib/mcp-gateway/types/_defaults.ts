// ─── Zenic-Agents v3 — MCP Gateway Type System ──────────────────────
// Default System Permissions and Roles

/** Resource action constants */
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
