import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { createHash } from "crypto";

/** Generate a SHA-256 content hash */
function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

export async function POST() {
  try {
    const results: string[] = [];

    // ─── 1. Seed Admin User ───────────────────────────────────────────
    let adminUser = await db.user.findUnique({ where: { email: "admin@zenic.dev" } });
    if (!adminUser) {
      adminUser = await db.user.create({
        data: {
          email: "admin@zenic.dev",
          name: "Admin User",
          status: "active",
          lastLogin: new Date(),
        },
      });
      results.push("Created admin user (admin@zenic.dev)");
    } else {
      results.push("Admin user already exists, skipping");
    }

    // ─── 2. Seed 4 Roles ─────────────────────────────────────────────
    const roleDefs = [
      { name: "superadmin", displayName: "Super Admin", description: "Full system access — no restrictions", color: "#dc2626", isSystem: true, priority: 100 },
      { name: "admin", displayName: "Admin", description: "Manage tools, policies, and roles", color: "#ea580c", isSystem: true, priority: 80 },
      { name: "operator", displayName: "Operator", description: "Execute tools and monitor system", color: "#0891b2", isSystem: true, priority: 50 },
      { name: "viewer", displayName: "Viewer", description: "Read-only access to tools and audit logs", color: "#6b7280", isSystem: true, priority: 10 },
    ];

    for (const rd of roleDefs) {
      const existing = await db.role.findUnique({ where: { name: rd.name } });
      if (!existing) {
        await db.role.create({ data: rd });
      }
    }
    results.push("Roles ensured (4 roles)");

    // ─── 3. Seed 18 Permissions ──────────────────────────────────────
    const permissionDefs = [
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

    const existingPermCount = await db.permission.count();
    if (existingPermCount === 0) {
      await db.permission.createMany({ data: permissionDefs });
      results.push(`Created ${permissionDefs.length} permissions`);
    } else {
      results.push(`Permissions already exist (${existingPermCount} found), skipping`);
    }

    // ─── 4. Seed 5 MCP Servers ───────────────────────────────────────
    const serverDefs = [
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

    const serverIds: string[] = [];
    for (const sd of serverDefs) {
      const server = await db.mcpServer.upsert({
        where: { name: sd.name },
        update: {},
        create: sd,
      });
      serverIds.push(server.id);
    }
    results.push(`Servers ensured (${serverIds.length} total)`);

    // ─── 5. Seed 10 MCP Tools ────────────────────────────────────────
    const toolDefs = [
      {
        name: "weather_lookup",
        displayName: "Weather Lookup",
        description: "Retrieve current weather conditions and forecasts for any global location",
        category: "external",
        version: "2.3.0",
        icon: "Cloud",
        endpoint: "/api/tools/weather",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { location: { type: "string" }, units: { type: "string", enum: ["celsius", "fahrenheit"] } }, required: ["location"] }),
        timeout: 10000,
        retries: 2,
        rateLimit: 60,
        riskLevel: "low",
        status: "active",
        requiresApproval: false,
        tags: JSON.stringify(["weather", "external", "api"]),
        metadata: JSON.stringify({ provider: "OpenWeatherMap", cacheTTL: 300 }),
        serverId: serverIds[0],
      },
      {
        name: "db_query",
        displayName: "Database Query",
        description: "Execute read-only SQL queries against authorized database connections with result pagination",
        category: "data",
        version: "1.8.2",
        icon: "Database",
        endpoint: "/api/tools/db/query",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { query: { type: "string" }, connectionId: { type: "string" }, limit: { type: "number", default: 100 } }, required: ["query", "connectionId"] }),
        timeout: 30000,
        retries: 1,
        rateLimit: 30,
        riskLevel: "medium",
        status: "active",
        requiresApproval: true,
        tags: JSON.stringify(["database", "sql", "read-only"]),
        metadata: JSON.stringify({ supportedDbs: ["postgresql", "mysql", "sqlite"] }),
        serverId: serverIds[0],
      },
      {
        name: "file_read",
        displayName: "File Reader",
        description: "Read file contents from authorized storage paths with format detection and encoding support",
        category: "storage",
        version: "1.5.1",
        icon: "FileText",
        endpoint: "/api/tools/file/read",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { path: { type: "string" }, encoding: { type: "string", default: "utf-8" } }, required: ["path"] }),
        timeout: 10000,
        retries: 2,
        rateLimit: 100,
        riskLevel: "medium",
        status: "active",
        requiresApproval: false,
        tags: JSON.stringify(["file", "storage", "read"]),
        metadata: JSON.stringify({ maxFileSize: "10MB", supportedEncodings: ["utf-8", "ascii", "base64"] }),
        serverId: serverIds[2],
      },
      {
        name: "email_send",
        displayName: "Email Sender",
        description: "Send templated emails to internal and external recipients with delivery tracking",
        category: "communication",
        version: "3.1.0",
        icon: "Mail",
        endpoint: "/api/tools/email/send",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { to: { type: "array", items: { type: "string" } }, subject: { type: "string" }, template: { type: "string" } }, required: ["to", "subject"] }),
        timeout: 15000,
        retries: 3,
        rateLimit: 20,
        riskLevel: "high",
        status: "active",
        requiresApproval: true,
        tags: JSON.stringify(["email", "communication", "notifications"]),
        metadata: JSON.stringify({ provider: "SendGrid", trackingEnabled: true }),
        serverId: serverIds[3],
      },
      {
        name: "compute_task",
        displayName: "Compute Task",
        description: "Submit and manage compute tasks including data processing, ML inference, and batch operations",
        category: "compute",
        version: "2.0.0",
        icon: "Cpu",
        endpoint: "/api/tools/compute",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { taskType: { type: "string", enum: ["data_processing", "ml_inference", "batch"] }, payload: { type: "object" } }, required: ["taskType", "payload"] }),
        timeout: 120000,
        retries: 1,
        rateLimit: 10,
        riskLevel: "high",
        status: "active",
        requiresApproval: true,
        tags: JSON.stringify(["compute", "ml", "processing"]),
        metadata: JSON.stringify({ maxMemory: "4GB", gpuAvailable: true }),
        serverId: serverIds[4],
      },
      {
        name: "security_scan",
        displayName: "Security Scanner",
        description: "Run vulnerability and compliance scans on target resources with detailed finding reports",
        category: "security",
        version: "1.2.0",
        icon: "Shield",
        endpoint: "/api/tools/security/scan",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { target: { type: "string" }, scanType: { type: "string", enum: ["vulnerability", "compliance", "full"] } }, required: ["target", "scanType"] }),
        timeout: 60000,
        retries: 1,
        rateLimit: 5,
        riskLevel: "critical",
        status: "active",
        requiresApproval: true,
        tags: JSON.stringify(["security", "scanning", "compliance"]),
        metadata: JSON.stringify({ scanEngines: ["nmap", "owasp-zap", "trivy"] }),
        serverId: serverIds[0],
      },
      {
        name: "metrics_collect",
        displayName: "Metrics Collector",
        description: "Collect and aggregate system metrics from monitoring endpoints with customizable time ranges",
        category: "monitoring",
        version: "1.4.0",
        icon: "Activity",
        endpoint: "/api/tools/metrics/collect",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { source: { type: "string" }, timeRange: { type: "string" }, granularity: { type: "string", default: "5m" } }, required: ["source", "timeRange"] }),
        timeout: 20000,
        retries: 2,
        rateLimit: 50,
        riskLevel: "low",
        status: "active",
        requiresApproval: false,
        tags: JSON.stringify(["monitoring", "metrics", "observability"]),
        metadata: JSON.stringify({ backends: ["prometheus", "grafana", "datadog"] }),
        serverId: serverIds[1],
      },
      {
        name: "webhook_dispatch",
        displayName: "Webhook Dispatcher",
        description: "Dispatch webhook events to registered endpoints with retry logic and delivery confirmation",
        category: "communication",
        version: "2.2.1",
        icon: "Webhook",
        endpoint: "/api/tools/webhook/dispatch",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { url: { type: "string" }, event: { type: "string" }, payload: { type: "object" } }, required: ["url", "event", "payload"] }),
        timeout: 10000,
        retries: 3,
        rateLimit: 100,
        riskLevel: "medium",
        status: "active",
        requiresApproval: false,
        tags: JSON.stringify(["webhook", "integration", "events"]),
        metadata: JSON.stringify({ maxRetries: 5, retryBackoff: "exponential" }),
        serverId: serverIds[0],
      },
      {
        name: "inventory_check",
        displayName: "Inventory Checker",
        description: "Check real-time inventory levels across warehouses and trigger restock alerts when thresholds are breached",
        category: "data",
        version: "1.1.0",
        icon: "Package",
        endpoint: "/api/tools/inventory/check",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { sku: { type: "string" }, warehouse: { type: "string" } }, required: ["sku"] }),
        timeout: 8000,
        retries: 2,
        rateLimit: 80,
        riskLevel: "low",
        status: "active",
        requiresApproval: false,
        tags: JSON.stringify(["inventory", "warehouse", "data"]),
        metadata: JSON.stringify({ realtimeSync: true, alertThreshold: 5 }),
        serverId: serverIds[2],
      },
      {
        name: "schema_mapper",
        displayName: "Schema Mapper",
        description: "Map and transform data schemas between systems with drift detection and auto-mitigation proposals",
        category: "data",
        version: "1.0.0",
        icon: "GitBranch",
        endpoint: "/api/tools/schema/mapper",
        method: "POST",
        inputSchema: JSON.stringify({ type: "object", properties: { sourceSchema: { type: "string" }, targetSchema: { type: "string" }, autoApply: { type: "boolean", default: false } }, required: ["sourceSchema", "targetSchema"] }),
        timeout: 15000,
        retries: 1,
        rateLimit: 20,
        riskLevel: "medium",
        status: "testing",
        requiresApproval: true,
        tags: JSON.stringify(["schema", "mapping", "drift-detection"]),
        metadata: JSON.stringify({ driftDetection: true, autoPropose: true }),
        serverId: serverIds[2],
      },
    ];

    const toolIds: string[] = [];
    for (const td of toolDefs) {
      const tool = await db.mcpTool.upsert({
        where: { name: td.name },
        update: {},
        create: td,
      });
      toolIds.push(tool.id);
    }
    results.push(`Tools ensured (${toolIds.length} total)`);

    // ─── 6. Seed 50 ToolExecutions ───────────────────────────────────
    const existingExecCount = await db.toolExecution.count();
    if (existingExecCount < 50 && toolIds.length > 0 && adminUser) {
      const now = Date.now();
      const executionData: Array<{
        toolIdx: number;
        status: string;
        duration: number | null;
        verdict: string | null;
        errorMessage: string | null;
        verdictReason: string | null;
        hoursAgo: number;
      }> = [];

      // Generate 50 realistic executions — mix of statuses
      const statusMix: Array<{ status: string; verdict: string | null; weight: number }> = [
        { status: "completed", verdict: "allow", weight: 35 },
        { status: "completed", verdict: "conditional", weight: 5 },
        { status: "failed", verdict: "allow", weight: 3 },
        { status: "denied", verdict: "deny", weight: 4 },
        { status: "timeout", verdict: "allow", weight: 2 },
        { status: "pending", verdict: null, weight: 1 },
      ];

      for (let i = 0; i < 50; i++) {
        // Pick status based on weighted distribution
        const rand = Math.random() * 50;
        let cumulative = 0;
        let chosen = statusMix[0];
        for (const sm of statusMix) {
          cumulative += sm.weight;
          if (rand < cumulative) { chosen = sm; break; }
        }

        const durationMap: Record<string, number | null> = {
          completed: Math.floor(Math.random() * 3000) + 50,
          failed: Math.floor(Math.random() * 5000) + 2000,
          denied: null,
          timeout: 30000,
          pending: null,
        };

        const errorMap: Record<string, string | null> = {
          completed: null,
          failed: ["Connection timeout after retries", "Service unavailable", "Rate limit exceeded", "Internal server error"][Math.floor(Math.random() * 4)],
          denied: null,
          timeout: "Execution exceeded 30s timeout",
          pending: null,
        };

        const reasonMap: Record<string, string | null> = {
          deny: ["Blocked by deny-external-after-hours policy", "Insufficient permissions", "Risk level exceeds threshold", "Quota exceeded"][Math.floor(Math.random() * 4)],
          conditional: "Requires approval per business-hours-only policy",
          allow: null,
        };

        executionData.push({
          toolIdx: i % toolIds.length,
          status: chosen.status,
          duration: durationMap[chosen.status] ?? null,
          verdict: chosen.verdict,
          errorMessage: errorMap[chosen.status],
          verdictReason: chosen.verdict ? reasonMap[chosen.verdict] : null,
          hoursAgo: Math.random() * 48, // spread across last 48 hours
        });
      }

      // Sort by hoursAgo descending (most recent first)
      executionData.sort((a, b) => a.hoursAgo - b.hoursAgo);

      await db.$transaction(
        executionData.map((exec) => {
          const toolId = toolIds[exec.toolIdx % toolIds.length];
          const createdAt = new Date(now - exec.hoursAgo * 60 * 60 * 1000);
          return db.toolExecution.create({
            data: {
              toolId,
              executorId: adminUser!.id,
              status: exec.status,
              input: JSON.stringify({ sample: true, executionSeed: true }),
              output: exec.status === "completed" ? JSON.stringify({ success: true, data: {} }) : null,
              errorMessage: exec.errorMessage,
              duration: exec.duration,
              verdict: exec.verdict,
              verdictReason: exec.verdictReason,
              createdAt,
              completedAt: ["completed", "failed", "denied", "timeout"].includes(exec.status)
                ? new Date(createdAt.getTime() + (exec.duration ?? 0))
                : null,
            },
          });
        })
      );
      results.push(`Created 50 sample tool executions`);
    } else if (existingExecCount >= 50) {
      results.push(`Tool executions already exist (${existingExecCount} found), skipping`);
    }

    // ─── 7. Seed 5 Pending HitlApprovalRequests (Memory Proposals) ───
    const existingHitlCount = await db.hitlApprovalRequest.count();
    if (existingHitlCount === 0 && adminUser) {
      const hitlData = [
        {
          requestId: "mp-001",
          title: "Schema Drift: Column 'monto_neto' missing",
          description: "Map 'monto_neto' to 'subtotal_neto' — detected drift in ERP→Analytics schema pipeline",
          type: "action_approval",
          status: "pending",
          priority: "medium",
          requesterId: adminUser.id,
          requesterName: "Memory Engine",
          targetResource: "schema_mapping",
          targetAction: "schema_drift",
          actionPayload: JSON.stringify({ source: "monto_neto", target: "subtotal_neto", confidence: 0.92 }),
          undoPayload: JSON.stringify({ revertMapping: true }),
          isReversible: true,
          approvalPolicy: JSON.stringify({ quorum: 1, autoApprove: false }),
          tags: JSON.stringify(["memory", "schema", "drift"]),
          metadata: JSON.stringify({ llmVerdict: true, engine: "memory-chip", driftType: "column_missing" }),
        },
        {
          requestId: "mp-002",
          title: "Intent Routing: 'consulta factura' → invoice_lookup",
          description: "Route 'consulta factura' intent to the invoice_lookup tool instead of db_query based on usage pattern analysis",
          type: "action_approval",
          status: "pending",
          priority: "high",
          requesterId: adminUser.id,
          requesterName: "Memory Engine",
          targetResource: "intent_routing",
          targetAction: "intent_reroute",
          actionPayload: JSON.stringify({ intent: "consulta factura", currentTarget: "db_query", proposedTarget: "invoice_lookup", sampleSize: 150 }),
          undoPayload: JSON.stringify({ revertRouting: true }),
          isReversible: true,
          approvalPolicy: JSON.stringify({ quorum: 1, autoApprove: false }),
          tags: JSON.stringify(["memory", "intent", "routing"]),
          metadata: JSON.stringify({ llmVerdict: true, engine: "memory-chip", confidence: 0.88 }),
        },
        {
          requestId: "mp-003",
          title: "Policy Refinement: Relax email_send rate limit",
          description: "Increase email_send rate limit from 20/min to 35/min for operator role based on zero-abuse history (90d window)",
          type: "policy_change",
          status: "pending",
          priority: "low",
          requesterId: adminUser.id,
          requesterName: "Memory Engine",
          targetResource: "access_policy",
          targetAction: "policy_refinement",
          actionPayload: JSON.stringify({ policyName: "rate-limit-operators", field: "quota.maxCalls", currentValue: 50, proposedValue: 80 }),
          undoPayload: JSON.stringify({ revertPolicy: true }),
          isReversible: true,
          approvalPolicy: JSON.stringify({ quorum: 2, autoApprove: false }),
          tags: JSON.stringify(["memory", "policy", "refinement"]),
          metadata: JSON.stringify({ llmVerdict: false, engine: "memory-chip", reasoning: "Zero abuse in 90d but needs dual approval" }),
        },
        {
          requestId: "mp-004",
          title: "Schema Drift: New table 'credit_notes' detected",
          description: "Auto-register 'credit_notes' table in the data catalog and map to existing invoice schema with credit_type discriminator",
          type: "action_approval",
          status: "pending",
          priority: "medium",
          requesterId: adminUser.id,
          requesterName: "Memory Engine",
          targetResource: "schema_mapping",
          targetAction: "schema_drift",
          actionPayload: JSON.stringify({ table: "credit_notes", discriminator: "credit_type", parentSchema: "invoice" }),
          undoPayload: JSON.stringify({ unregisterTable: "credit_notes" }),
          isReversible: true,
          approvalPolicy: JSON.stringify({ quorum: 1, autoApprove: false }),
          tags: JSON.stringify(["memory", "schema", "drift"]),
          metadata: JSON.stringify({ llmVerdict: true, engine: "memory-chip", driftType: "table_added" }),
        },
        {
          requestId: "mp-005",
          title: "Intent Routing: 'estado pedido' → order_tracker",
          description: "Create new intent mapping 'estado pedido' → order_tracker tool (currently unhandled, 47 missed requests in 7 days)",
          type: "action_approval",
          status: "pending",
          priority: "high",
          requesterId: adminUser.id,
          requesterName: "Memory Engine",
          targetResource: "intent_routing",
          targetAction: "intent_create",
          actionPayload: JSON.stringify({ intent: "estado pedido", proposedTarget: "order_tracker", missedRequests: 47, period: "7d" }),
          undoPayload: JSON.stringify({ removeIntent: "estado pedido" }),
          isReversible: true,
          approvalPolicy: JSON.stringify({ quorum: 1, autoApprove: false }),
          tags: JSON.stringify(["memory", "intent", "routing"]),
          metadata: JSON.stringify({ llmVerdict: true, engine: "memory-chip", confidence: 0.95 }),
        },
      ];

      for (const h of hitlData) {
        await db.hitlApprovalRequest.create({ data: h });
      }
      results.push(`Created 5 pending HITL approval requests (memory proposals)`);
    } else if (existingHitlCount > 0) {
      results.push(`HITL approval requests already exist (${existingHitlCount} found), skipping`);
    }

    // ─── 8. Seed 20 AuditLog Entries ─────────────────────────────────
    const existingAuditCount = await db.auditLog.count();
    if (existingAuditCount === 0 && adminUser) {
      const now = Date.now();
      const auditEntries = [
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "weather_lookup", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "weather_lookup", verdict: "allow", duration: 450 }), tags: JSON.stringify(["execution"]), hoursAgo: 0.5 },
        { actorId: "system", actorType: "system", action: "policy.evaluate", resource: "policy", resourceName: "business-hours-only", severity: "info", outcome: "success", details: JSON.stringify({ policyName: "business-hours-only", verdict: "allow" }), tags: JSON.stringify(["policy"]), hoursAgo: 1 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "db_query", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "db_query", verdict: "allow", duration: 1200 }), tags: JSON.stringify(["execution"]), hoursAgo: 1.5 },
        { actorId: "system", actorType: "system", action: "policy.evaluate", resource: "policy", resourceName: "deny-external-after-hours", severity: "warn", outcome: "denied", details: JSON.stringify({ policyName: "deny-external-after-hours", reason: "After hours restriction" }), tags: JSON.stringify(["policy", "denied"]), hoursAgo: 2 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "file_read", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "file_read", verdict: "allow", duration: 230 }), tags: JSON.stringify(["execution"]), hoursAgo: 3 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "compute_task", severity: "error", outcome: "failure", details: JSON.stringify({ toolName: "compute_task", error: "Connection timeout after retries", duration: 5000 }), tags: JSON.stringify(["execution", "error"]), hoursAgo: 4 },
        { actorId: "system", actorType: "system", action: "security.alert", resource: "tool", resourceName: "security_scan", severity: "critical", outcome: "denied", details: JSON.stringify({ alert: "Unauthorized execution attempt", toolName: "security_scan", blockedBy: "RBAC" }), tags: JSON.stringify(["security", "alert", "critical"]), hoursAgo: 5 },
        { actorId: "system", actorType: "system", action: "server.health_check", resource: "server", resourceName: "primary-gateway", severity: "info", outcome: "success", details: JSON.stringify({ serverName: "primary-gateway", status: "healthy", responseTime: 45 }), tags: JSON.stringify(["monitoring", "health"]), hoursAgo: 6 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "metrics_collect", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "metrics_collect", verdict: "allow", duration: 890 }), tags: JSON.stringify(["execution"]), hoursAgo: 8 },
        { actorId: adminUser.id, actorType: "user", action: "policy.create", resource: "policy", resourceName: "business-hours-only", severity: "info", outcome: "success", details: JSON.stringify({ policyName: "business-hours-only", effect: "require_approval" }), tags: JSON.stringify(["policy"]), hoursAgo: 10 },
        { actorId: "system", actorType: "system", action: "tool.execute", resource: "tool", resourceName: "email_send", severity: "warn", outcome: "denied", details: JSON.stringify({ toolName: "email_send", verdict: "deny", reason: "Rate limit exceeded" }), tags: JSON.stringify(["execution", "rate-limit"]), hoursAgo: 12 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "webhook_dispatch", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "webhook_dispatch", verdict: "allow", duration: 320 }), tags: JSON.stringify(["execution"]), hoursAgo: 14 },
        { actorId: "system", actorType: "system", action: "resource.low_stock", resource: "inventory", resourceName: "Inventory", severity: "warn", outcome: "success", details: JSON.stringify({ alert: "Low stock (5 items)", sku: "WH-0042" }), tags: JSON.stringify(["inventory", "alert"]), hoursAgo: 16 },
        { actorId: adminUser.id, actorType: "user", action: "role.assign", resource: "role", resourceName: "superadmin", severity: "info", outcome: "success", details: JSON.stringify({ targetUserId: adminUser.id, role: "superadmin" }), tags: JSON.stringify(["rbac"]), hoursAgo: 18 },
        { actorId: "system", actorType: "system", action: "server.health_check", resource: "server", resourceName: "notification-hub", severity: "error", outcome: "failure", details: JSON.stringify({ serverName: "notification-hub", status: "unhealthy", error: "SMTP timeout" }), tags: JSON.stringify(["monitoring", "health", "error"]), hoursAgo: 20 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "inventory_check", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "inventory_check", verdict: "allow", duration: 150 }), tags: JSON.stringify(["execution"]), hoursAgo: 22 },
        { actorId: "system", actorType: "system", action: "security.alert", resource: "tool", resourceName: "compute_task", severity: "critical", outcome: "denied", details: JSON.stringify({ alert: "GPU resource abuse attempt", toolName: "compute_task", blockedBy: "Policy Engine" }), tags: JSON.stringify(["security", "alert", "critical"]), hoursAgo: 23 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "schema_mapper", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "schema_mapper", verdict: "conditional", duration: 1200 }), tags: JSON.stringify(["execution"]), hoursAgo: 30 },
        { actorId: "system", actorType: "system", action: "policy.evaluate", resource: "policy", resourceName: "rate-limit-operators", severity: "warn", outcome: "success", details: JSON.stringify({ policyName: "rate-limit-operators", remainingQuota: 3, window: "1h" }), tags: JSON.stringify(["policy", "quota"]), hoursAgo: 36 },
        { actorId: adminUser.id, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "weather_lookup", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "weather_lookup", verdict: "allow", duration: 380 }), tags: JSON.stringify(["execution"]), hoursAgo: 40 },
      ];

      await db.auditLog.createMany({
        data: auditEntries.map((entry) => ({
          actorId: entry.actorType === "user" ? entry.actorId : null,
          actorType: entry.actorType,
          action: entry.action,
          resource: entry.resource,
          resourceName: entry.resourceName,
          severity: entry.severity,
          outcome: entry.outcome,
          details: entry.details,
          tags: entry.tags,
          createdAt: new Date(now - entry.hoursAgo * 60 * 60 * 1000),
        })),
      });
      results.push(`Created 20 audit log entries`);
    } else if (existingAuditCount > 0) {
      results.push(`Audit logs already exist (${existingAuditCount} found), skipping`);
    }

    // ─── 9. Seed 5 HitlApprovalAudit Entries with Merkle Chain ───────
    const existingAuditTrailCount = await db.hitlApprovalAudit.count();
    if (existingAuditTrailCount === 0 && adminUser) {
      // Get the HITL requests we just created
      const hitlRequests = await db.hitlApprovalRequest.findMany({ take: 5 });
      if (hitlRequests.length > 0) {
        const auditEvents = [
          { requestId: hitlRequests[0].requestId, eventType: "created", actorId: adminUser.id, actorName: "Memory Engine", details: JSON.stringify({ proposal: "Schema Drift detected" }) },
          { requestId: hitlRequests[1].requestId, eventType: "created", actorId: adminUser.id, actorName: "Memory Engine", details: JSON.stringify({ proposal: "Intent Routing update" }) },
          { requestId: hitlRequests[0].requestId, eventType: "approved", actorId: adminUser.id, actorName: "Admin User", details: JSON.stringify({ approvedBy: "Admin User", comment: "Looks good, mapping is correct" }) },
          { requestId: hitlRequests[2].requestId, eventType: "created", actorId: adminUser.id, actorName: "Memory Engine", details: JSON.stringify({ proposal: "Policy Refinement request" }) },
          { requestId: hitlRequests[1].requestId, eventType: "approved", actorId: adminUser.id, actorName: "Admin User", details: JSON.stringify({ approvedBy: "Admin User", comment: "Routing makes sense based on usage data" }) },
        ];

        let previousHash: string | null = null;
        const now = Date.now();

        for (let i = 0; i < auditEvents.length; i++) {
          const evt = auditEvents[i];
          const content = JSON.stringify({
            requestId: evt.requestId,
            eventType: evt.eventType,
            actorName: evt.actorName,
            details: evt.details,
            previousHash,
            index: i,
          });
          const contentHash = sha256(content);

          await db.hitlApprovalAudit.create({
            data: {
              requestId: evt.requestId,
              eventType: evt.eventType,
              actorId: evt.actorId,
              actorName: evt.actorName,
              details: evt.details,
              contentHash,
              previousHash,
              timestamp: new Date(now - (auditEvents.length - i) * 30 * 60 * 1000), // 30 min intervals
            },
          });

          previousHash = contentHash;
        }
        results.push(`Created 5 Merkle-chain audit trail entries`);
      }
    } else if (existingAuditTrailCount > 0) {
      results.push(`HITL audit trail already exists (${existingAuditTrailCount} found), skipping`);
    }

    // ─── 10. Seed 8 MetricSeries with MetricPoints ───────────────────
    const existingSeriesCount = await db.metricSeries.count();
    if (existingSeriesCount === 0) {
      const seriesDefs = [
        { name: "gateway.deny_rate", description: "Percentage of tool executions denied by policy engine", category: "security", unit: "percent", labels: JSON.stringify({}) },
        { name: "gateway.execution_throughput", description: "Number of tool executions per minute", category: "operational", unit: "count", labels: JSON.stringify({}) },
        { name: "business.cost_per_flow", description: "Average cost per automated flow execution", category: "business", unit: "usd", labels: JSON.stringify({}) },
        { name: "gateway.avg_latency", description: "Average gateway latency in milliseconds", category: "operational", unit: "ms", labels: JSON.stringify({}) },
        { name: "security.critical_alerts", description: "Number of critical security alerts in the last hour", category: "security", unit: "count", labels: JSON.stringify({}) },
        { name: "resilience.error_rate", description: "Error rate across all tool executions", category: "resilience", unit: "percent", labels: JSON.stringify({}) },
        { name: "business.approval_time", description: "Average time to approve HITL requests in minutes", category: "business", unit: "ms", labels: JSON.stringify({}) },
        { name: "gateway.conditional_verdicts", description: "Rate of conditional verdicts requiring approval", category: "operational", unit: "percent", labels: JSON.stringify({}) },
      ];

      const now = Date.now();

      for (const sd of seriesDefs) {
        const series = await db.metricSeries.create({ data: sd });

        // Create 24 hourly data points for each series
        const points = [];
        for (let h = 0; h < 24; h++) {
          let value: number;
          // Generate realistic values based on metric type
          switch (sd.unit) {
            case "percent":
              value = Math.round((Math.random() * 5 + 0.5) * 100) / 100; // 0.5-5.5%
              break;
            case "ms":
              value = Math.round(Math.random() * 100 + 20); // 20-120ms
              break;
            case "usd":
              value = Math.round((Math.random() * 0.5 + 0.05) * 1000) / 1000; // $0.05-$0.55
              break;
            case "count":
            default:
              value = Math.round(Math.random() * 50 + 5); // 5-55
              break;
          }

          points.push({
            seriesId: series.id,
            value,
            labels: JSON.stringify({ hour: `${h.toString().padStart(2, "0")}:00` }),
            timestamp: new Date(now - (23 - h) * 60 * 60 * 1000),
          });
        }

        await db.metricPoint.createMany({ data: points });
      }
      results.push(`Created 8 metric series with 24 data points each (192 total points)`);
    } else {
      results.push(`Metric series already exist (${existingSeriesCount} found), skipping`);
    }

    return NextResponse.json({
      success: true,
      data: { results },
      message: "Database seeding completed (idempotent)",
    });
  } catch (error) {
    console.error("[/api/seed POST]", error);
    return NextResponse.json(
      {
        error: "Failed to seed database",
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}
