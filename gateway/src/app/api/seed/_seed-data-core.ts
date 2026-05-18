// ─── Seed Data — Core Definitions ──────────────────────────────────────
// Roles, permissions, servers, and metric series definitions.
// Extracted from _seed-data.ts to stay under 400 lines.

export const ROLE_DEFS = [
  { name: "superadmin", displayName: "Super Admin", description: "Full system access — no restrictions", color: "#dc2626", isSystem: true, priority: 100 },
  { name: "admin", displayName: "Admin", description: "Manage tools, policies, and roles", color: "#ea580c", isSystem: true, priority: 80 },
  { name: "operator", displayName: "Operator", description: "Execute tools and monitor system", color: "#0891b2", isSystem: true, priority: 50 },
  { name: "viewer", displayName: "Viewer", description: "Read-only access to tools and audit logs", color: "#6b7280", isSystem: true, priority: 10 },
];

export const PERMISSION_DEFS = [
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

export function getServerDefs(): Array<{
  name: string;
  displayName: string;
  description: string;
  url: string;
  protocol: string;
  status: string;
  healthCheckUrl: string;
  authType: string;
  authConfig: string;
  capabilities: string;
  metadata: string;
}> {
  return [
    {
      name: "primary-gateway",
      displayName: "Primary Gateway",
      description: "Main MCP gateway server handling tool routing and execution for core services",
      url: "https://mcp-gateway.zenic.dev",
      protocol: "http",
      status: "active",
      healthCheckUrl: "https://mcp-gateway.zenic.dev/health",
      authType: "api_key",
      authConfig: JSON.stringify({ header: "X-API-Key", rotationDays: 30 }),
      capabilities: JSON.stringify(["tool_execution", "streaming", "batch", "cancellation"]),
      metadata: JSON.stringify({ region: "us-east-1", version: "3.2.1", uptime: "99.97%" }),
    },
    {
      name: "analytics-relay",
      displayName: "Analytics Relay",
      description: "Secondary relay server for analytics and monitoring tool execution",
      url: "wss://analytics.zenic.dev/ws",
      protocol: "websocket",
      status: "active",
      healthCheckUrl: "https://analytics.zenic.dev/health",
      authType: "oauth2",
      authConfig: JSON.stringify({ provider: "internal", scopes: ["read", "execute"] }),
      capabilities: JSON.stringify(["analytics", "monitoring", "realtime", "alerts"]),
      metadata: JSON.stringify({ region: "eu-west-1", version: "2.1.0", uptime: "99.85%" }),
    },
    {
      name: "data-lake-connector",
      displayName: "Data Lake Connector",
      description: "Connector service for data lake read/write operations with schema validation",
      url: "https://datalake.zenic.dev",
      protocol: "http",
      status: "active",
      healthCheckUrl: "https://datalake.zenic.dev/health",
      authType: "mtls",
      authConfig: JSON.stringify({ certRotation: "30d" }),
      capabilities: JSON.stringify(["data_read", "data_write", "schema_validation", "batch_import"]),
      metadata: JSON.stringify({ region: "us-west-2", version: "1.3.0", uptime: "99.92%" }),
    },
    {
      name: "notification-hub",
      displayName: "Notification Hub",
      description: "Central notification service for email, SMS, and push delivery",
      url: "https://notify.zenic.dev",
      protocol: "http",
      status: "unhealthy",
      healthCheckUrl: "https://notify.zenic.dev/health",
      authType: "api_key",
      authConfig: JSON.stringify({ header: "X-Notify-Key" }),
      capabilities: JSON.stringify(["email", "sms", "push", "webhook"]),
      metadata: JSON.stringify({ region: "ap-south-1", version: "1.1.0", uptime: "97.5%", lastError: "SMTP timeout" }),
    },
    {
      name: "compute-cluster",
      displayName: "Compute Cluster",
      description: "GPU-enabled compute cluster for ML inference and batch processing",
      url: "grpc://compute.zenic.dev:50051",
      protocol: "grpc",
      status: "active",
      healthCheckUrl: "https://compute.zenic.dev/health",
      authType: "mtls",
      authConfig: JSON.stringify({ certRotation: "7d" }),
      capabilities: JSON.stringify(["ml_inference", "batch_processing", "gpu_compute", "auto_scaling"]),
      metadata: JSON.stringify({ region: "us-east-1", version: "2.0.0", uptime: "99.99%", gpuAvailable: true }),
    },
  ];
}

export const SERIES_DEFS = [
  { name: "gateway.deny_rate", description: "Percentage of tool executions denied by policy engine", category: "security", unit: "percent", labels: JSON.stringify({}) },
  { name: "gateway.execution_throughput", description: "Number of tool executions per minute", category: "operational", unit: "count", labels: JSON.stringify({}) },
  { name: "business.cost_per_flow", description: "Average cost per automated flow execution", category: "business", unit: "usd", labels: JSON.stringify({}) },
  { name: "gateway.avg_latency", description: "Average gateway latency in milliseconds", category: "operational", unit: "ms", labels: JSON.stringify({}) },
  { name: "security.critical_alerts", description: "Number of critical security alerts in the last hour", category: "security", unit: "count", labels: JSON.stringify({}) },
  { name: "resilience.error_rate", description: "Error rate across all tool executions", category: "resilience", unit: "percent", labels: JSON.stringify({}) },
  { name: "business.approval_time", description: "Average time to approve HITL requests in minutes", category: "business", unit: "ms", labels: JSON.stringify({}) },
  { name: "gateway.conditional_verdicts", description: "Rate of conditional verdicts requiring approval", category: "operational", unit: "percent", labels: JSON.stringify({}) },
];
