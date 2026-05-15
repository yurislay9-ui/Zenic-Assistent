import { NextResponse } from "next/server";
import { db } from "@/lib/db";
import { DEFAULT_PERMISSIONS, DEFAULT_ROLES } from "@/lib/mcp-gateway/types";
import { recordAudit, recordAuditBatch } from "@/lib/mcp-gateway/services/audit-service";

export async function POST() {
  try {
    const results: string[] = [];

    // ─── 1. Seed Permissions ───────────────────────────────────────────
    const existingPermCount = await db.permission.count();
    if (existingPermCount === 0) {
      await db.permission.createMany({
        data: DEFAULT_PERMISSIONS.map((p) => ({
          name: p.name,
          resource: p.resource,
          action: p.action,
          displayName: p.displayName,
          description: p.description,
          isDangerous: p.isDangerous,
        })),
      });
      results.push(`Created ${DEFAULT_PERMISSIONS.length} permissions`);
    } else {
      results.push(`Permissions already exist (${existingPermCount} found), skipping`);
    }

    // ─── 2. Seed Roles with Permission Links ──────────────────────────
    const existingRoleCount = await db.role.count();
    if (existingRoleCount === 0) {
      // Fetch all permissions to get their IDs
      const allPermissions = await db.permission.findMany();
      const permMap = new Map(allPermissions.map((p) => [p.name, p.id]));

      for (const roleDef of DEFAULT_ROLES) {
        const permissionIds = roleDef.permissionNames
          .map((name) => permMap.get(name))
          .filter((id): id is string => id !== undefined);

        await db.role.create({
          data: {
            name: roleDef.name,
            displayName: roleDef.displayName,
            description: roleDef.description,
            color: roleDef.color,
            isSystem: roleDef.isSystem,
            priority: roleDef.priority,
            permissions: {
              create: permissionIds.map((permId) => ({
                permissionId: permId,
              })),
            },
          },
        });
      }
      results.push(`Created ${DEFAULT_ROLES.length} default roles`);
    } else {
      results.push(`Roles already exist (${existingRoleCount} found), skipping`);
    }

    // ─── 3. Seed Demo Users ──────────────────────────────────────────
    let adminUser = await db.user.findUnique({ where: { email: "admin@zenic.dev" } });
    if (!adminUser) {
      adminUser = await db.user.create({
        data: {
          email: "admin@zenic.dev",
          name: "Admin",
          status: "active",
          lastLogin: new Date(),
        },
      });
      results.push("Created demo admin user (admin@zenic.dev)");
    } else {
      results.push("Demo admin user already exists, skipping");
    }

    // Additional demo users
    const demoUsers = [
      { email: "operator@zenic.dev", name: "Operator" },
      { email: "viewer@zenic.dev", name: "Viewer" },
      { email: "dev@zenic.dev", name: "Developer" },
    ];
    for (const du of demoUsers) {
      const existing = await db.user.findUnique({ where: { email: du.email } });
      if (!existing) {
        await db.user.create({ data: { email: du.email, name: du.name, status: "active" } });
      }
    }

    // Assign roles to demo users
    const operatorRole = await db.role.findUnique({ where: { name: "operator" } });
    const viewerRole = await db.role.findUnique({ where: { name: "viewer" } });
    const adminRole = await db.role.findUnique({ where: { name: "admin" } });

    const operatorUser = await db.user.findUnique({ where: { email: "operator@zenic.dev" } });
    const viewerUser = await db.user.findUnique({ where: { email: "viewer@zenic.dev" } });
    const devUser = await db.user.findUnique({ where: { email: "dev@zenic.dev" } });

    if (operatorRole && operatorUser) {
      const exists = await db.userRole.findUnique({
        where: { userId_roleId: { userId: operatorUser.id, roleId: operatorRole.id } },
      });
      if (!exists) await db.userRole.create({ data: { userId: operatorUser.id, roleId: operatorRole.id, grantedBy: "system" } });
    }
    if (viewerRole && viewerUser) {
      const exists = await db.userRole.findUnique({
        where: { userId_roleId: { userId: viewerUser.id, roleId: viewerRole.id } },
      });
      if (!exists) await db.userRole.create({ data: { userId: viewerUser.id, roleId: viewerRole.id, grantedBy: "system" } });
    }
    if (adminRole && devUser) {
      const exists = await db.userRole.findUnique({
        where: { userId_roleId: { userId: devUser.id, roleId: adminRole.id } },
      });
      if (!exists) await db.userRole.create({ data: { userId: devUser.id, roleId: adminRole.id, grantedBy: "system" } });
    }

    // ─── 4. Assign Superadmin Role to Admin User ──────────────────────
    const superadminRole = await db.role.findUnique({ where: { name: "superadmin" } });
    if (superadminRole && adminUser) {
      const existingAssignment = await db.userRole.findUnique({
        where: { userId_roleId: { userId: adminUser.id, roleId: superadminRole.id } },
      });
      if (!existingAssignment) {
        await db.userRole.create({
          data: {
            userId: adminUser.id,
            roleId: superadminRole.id,
            grantedBy: "system",
          },
        });
        results.push("Assigned superadmin role to demo admin user");
      } else {
        results.push("Superadmin role already assigned to demo admin, skipping");
      }
    }

    // ─── 5. Seed MCP Servers (upsert) ──────────────────────────────────
    let server1Id: string | undefined;
    let server2Id: string | undefined;

    {
      // Upsert servers by name
      const s1 = await db.mcpServer.upsert({
        where: { name: "primary-gateway" },
        update: {},
        create: {
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
      });

      const s2 = await db.mcpServer.upsert({
        where: { name: "analytics-relay" },
        update: {},
        create: {
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
      });

      server1Id = s1.id;
      server2Id = s2.id;
      const totalServers = await db.mcpServer.count();
      results.push(`Servers ready (${totalServers} total)`);
    }

    // ─── 6. Seed MCP Tools (upsert by name) ────────────────────────────
    let toolIds: string[] = [];

    {
      const sampleTools = [
        {
          name: "weather_lookup",
          displayName: "Weather Lookup",
          description: "Retrieve current weather conditions and forecasts for any global location",
          category: "external",
          version: "2.3.0",
          icon: "Cloud",
          endpoint: "/api/tools/weather",
          method: "POST",
          inputSchema: JSON.stringify({
            type: "object",
            properties: { location: { type: "string" }, units: { type: "string", enum: ["celsius", "fahrenheit"] } },
            required: ["location"],
          }),
          timeout: 10000,
          retries: 2,
          rateLimit: 60,
          riskLevel: "low",
          status: "active",
          requiresApproval: false,
          tags: JSON.stringify(["weather", "external", "api"]),
          metadata: JSON.stringify({ provider: "OpenWeatherMap", cacheTTL: 300 }),
          serverId: server1Id,
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
          inputSchema: JSON.stringify({
            type: "object",
            properties: { query: { type: "string" }, connectionId: { type: "string" }, limit: { type: "number", default: 100 } },
            required: ["query", "connectionId"],
          }),
          timeout: 30000,
          retries: 1,
          rateLimit: 30,
          riskLevel: "medium",
          status: "active",
          requiresApproval: true,
          tags: JSON.stringify(["database", "sql", "read-only"]),
          metadata: JSON.stringify({ supportedDbs: ["postgresql", "mysql", "sqlite"] }),
          serverId: server1Id,
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
          inputSchema: JSON.stringify({
            type: "object",
            properties: { to: { type: "array", items: { type: "string" } }, subject: { type: "string" }, template: { type: "string" } },
            required: ["to", "subject"],
          }),
          timeout: 15000,
          retries: 3,
          rateLimit: 20,
          riskLevel: "high",
          status: "active",
          requiresApproval: true,
          tags: JSON.stringify(["email", "communication", "notifications"]),
          metadata: JSON.stringify({ provider: "SendGrid", trackingEnabled: true }),
          serverId: server1Id,
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
          inputSchema: JSON.stringify({
            type: "object",
            properties: { path: { type: "string" }, encoding: { type: "string", default: "utf-8" } },
            required: ["path"],
          }),
          timeout: 10000,
          retries: 2,
          rateLimit: 100,
          riskLevel: "medium",
          status: "active",
          requiresApproval: false,
          tags: JSON.stringify(["file", "storage", "read"]),
          metadata: JSON.stringify({ maxFileSize: "10MB", supportedEncodings: ["utf-8", "ascii", "base64"] }),
          serverId: server1Id,
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
          inputSchema: JSON.stringify({
            type: "object",
            properties: { taskType: { type: "string", enum: ["data_processing", "ml_inference", "batch"] }, payload: { type: "object" } },
            required: ["taskType", "payload"],
          }),
          timeout: 120000,
          retries: 1,
          rateLimit: 10,
          riskLevel: "high",
          status: "active",
          requiresApproval: true,
          tags: JSON.stringify(["compute", "ml", "processing"]),
          metadata: JSON.stringify({ maxMemory: "4GB", gpuAvailable: true }),
          serverId: server2Id,
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
          inputSchema: JSON.stringify({
            type: "object",
            properties: { target: { type: "string" }, scanType: { type: "string", enum: ["vulnerability", "compliance", "full"] } },
            required: ["target", "scanType"],
          }),
          timeout: 60000,
          retries: 1,
          rateLimit: 5,
          riskLevel: "critical",
          status: "active",
          requiresApproval: true,
          tags: JSON.stringify(["security", "scanning", "compliance"]),
          metadata: JSON.stringify({ scanEngines: ["nmap", "owasp-zap", "trivy"] }),
          serverId: server2Id,
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
          inputSchema: JSON.stringify({
            type: "object",
            properties: { source: { type: "string" }, timeRange: { type: "string" }, granularity: { type: "string", default: "5m" } },
            required: ["source", "timeRange"],
          }),
          timeout: 20000,
          retries: 2,
          rateLimit: 50,
          riskLevel: "low",
          status: "active",
          requiresApproval: false,
          tags: JSON.stringify(["monitoring", "metrics", "observability"]),
          metadata: JSON.stringify({ backends: ["prometheus", "grafana", "datadog"] }),
          serverId: server2Id,
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
          inputSchema: JSON.stringify({
            type: "object",
            properties: { url: { type: "string" }, event: { type: "string" }, payload: { type: "object" } },
            required: ["url", "event", "payload"],
          }),
          timeout: 10000,
          retries: 3,
          rateLimit: 100,
          riskLevel: "medium",
          status: "active",
          requiresApproval: false,
          tags: JSON.stringify(["webhook", "integration", "events"]),
          metadata: JSON.stringify({ maxRetries: 5, retryBackoff: "exponential" }),
          serverId: server1Id,
        },
      ];

      // Upsert tools by name — creates missing, updates existing
      let created = 0;
      let updated = 0;
      for (const tool of sampleTools) {
        const existing = await db.mcpTool.findUnique({ where: { name: tool.name } });
        if (existing) {
          await db.mcpTool.update({ where: { name: tool.name }, data: tool });
          updated++;
        } else {
          await db.mcpTool.create({ data: tool });
          created++;
        }
      }
      // Clean up stale tools from earlier seeds
      const desiredNames = sampleTools.map((t) => t.name);
      const staleDelete = await db.mcpTool.deleteMany({
        where: { name: { notIn: desiredNames } },
      });
      const allTools = await db.mcpTool.findMany();
      toolIds = allTools.map((t) => t.id);
      const extraMsg = staleDelete.count > 0 ? `, removed ${staleDelete.count} stale` : "";
      results.push(`Tools: ${created} created, ${updated} updated (${allTools.length} total${extraMsg})`);
    }

    // ─── 7. Seed Access Policies ──────────────────────────────────────
    const existingPolicyCount = await db.accessPolicy.count();
    if (existingPolicyCount === 0 && toolIds.length > 0) {
      const samplePolicies = [
        {
          name: "business-hours-only",
          description: "Restrict high-risk tool execution to business hours (9AM-6PM UTC)",
          type: "conditional",
          priority: 90,
          isEnabled: true,
          conditions: JSON.stringify([
            { field: "riskLevel", operator: "in", value: ["high", "critical"] },
          ]),
          effect: "require_approval",
          timeWindow: JSON.stringify({ start: "09:00", end: "18:00", tz: "UTC" }),
          quota: null,
        },
        {
          name: "rate-limit-operators",
          description: "Enforce call rate quotas for operator-level users on data tools",
          type: "quota",
          priority: 70,
          isEnabled: true,
          conditions: JSON.stringify([
            { field: "executorRole", operator: "eq", value: "operator" },
            { field: "category", operator: "eq", value: "data" },
          ]),
          effect: "allow",
          timeWindow: null,
          quota: JSON.stringify({ maxCalls: 50, window: "1h" }),
        },
        {
          name: "deny-external-after-hours",
          description: "Block external API calls outside of standard working hours to reduce attack surface",
          type: "deny",
          priority: 80,
          isEnabled: true,
          conditions: JSON.stringify([
            { field: "category", operator: "eq", value: "external" },
          ]),
          effect: "deny",
          timeWindow: JSON.stringify({ start: "18:00", end: "09:00", tz: "UTC" }),
          quota: null,
        },
      ];

      for (const policyDef of samplePolicies) {
        await db.accessPolicy.create({
          data: {
            name: policyDef.name,
            description: policyDef.description,
            type: policyDef.type,
            priority: policyDef.priority,
            isEnabled: policyDef.isEnabled,
            conditions: policyDef.conditions,
            effect: policyDef.effect,
            timeWindow: policyDef.timeWindow,
            quota: policyDef.quota,
            toolAccessPolicies: {
              create: toolIds.map((toolId) => ({ toolId })),
            },
          },
        });
      }
      results.push("Created 3 sample access policies");
    } else if (existingPolicyCount > 0) {
      results.push(`Access policies already exist (${existingPolicyCount} found), skipping`);
    } else {
      results.push("No tools available to create policies, skipping");
    }

    // ─── 8. Seed Tool Executions ──────────────────────────────────────
    const existingExecCount = await db.toolExecution.count();
    if (existingExecCount === 0 && toolIds.length > 0 && adminUser) {
      const now = Date.now();
      const executionData = [
        { toolIdx: 0, status: "completed", duration: 450, verdict: "allow", hoursAgo: 0.5 },
        { toolIdx: 1, status: "completed", duration: 1200, verdict: "allow", hoursAgo: 1 },
        { toolIdx: 2, status: "pending", duration: null, verdict: null, hoursAgo: 1.5 },
        { toolIdx: 3, status: "completed", duration: 230, verdict: "allow", hoursAgo: 2 },
        { toolIdx: 0, status: "completed", duration: 380, verdict: "allow", hoursAgo: 3 },
        { toolIdx: 4, status: "failed", duration: 5000, verdict: "allow", hoursAgo: 4 },
        { toolIdx: 5, status: "denied", duration: null, verdict: "deny", hoursAgo: 5 },
        { toolIdx: 6, status: "completed", duration: 890, verdict: "allow", hoursAgo: 6 },
        { toolIdx: 1, status: "completed", duration: 1500, verdict: "allow", hoursAgo: 8 },
        { toolIdx: 7, status: "completed", duration: 320, verdict: "allow", hoursAgo: 10 },
        { toolIdx: 0, status: "timeout", duration: 30000, verdict: "allow", hoursAgo: 12 },
        { toolIdx: 3, status: "completed", duration: 180, verdict: "allow", hoursAgo: 14 },
      ];

      await db.$transaction(
        executionData.map((exec) => {
          const toolId = toolIds[exec.toolIdx % toolIds.length];
          const createdAt = new Date(now - exec.hoursAgo * 60 * 60 * 1000);
          return db.toolExecution.create({
            data: {
              toolId,
              executorId: adminUser.id,
              status: exec.status,
              input: JSON.stringify({ sample: true }),
              output: exec.status === "completed" ? JSON.stringify({ success: true, data: {} }) : null,
              errorMessage: exec.status === "failed" ? "Connection timeout after retries" : null,
              duration: exec.duration,
              verdict: exec.verdict,
              verdictReason: exec.verdict === "deny" ? "Blocked by deny-external-after-hours policy" : null,
              createdAt,
              completedAt: exec.status === "completed" || exec.status === "failed" || exec.status === "denied" || exec.status === "timeout"
                ? new Date(createdAt.getTime() + (exec.duration ?? 0))
                : null,
            },
          });
        })
      );
      results.push(`Created ${executionData.length} sample tool executions`);
    } else if (existingExecCount > 0) {
      results.push(`Tool executions already exist (${existingExecCount} found), skipping`);
    }

    // ─── 9. Seed Audit Logs ───────────────────────────────────────────
    const existingAuditCount = await db.auditLog.count();
    if (existingAuditCount === 0 && adminUser) {
      const now = Date.now();
      const auditEntries = [
        {
          actorId: adminUser.id,
          actorType: "user",
          action: "tool.execute",
          resource: "tool",
          severity: "info",
          outcome: "success",
          details: JSON.stringify({ toolName: "weather_lookup", verdict: "allow" }),
          tags: JSON.stringify(["execution"]),
          hoursAgo: 0.5,
        },
        {
          actorId: adminUser.id,
          actorType: "user",
          action: "role.assign",
          resource: "role",
          severity: "info",
          outcome: "success",
          details: JSON.stringify({ targetUserId: adminUser.id, role: "superadmin" }),
          tags: JSON.stringify(["rbac"]),
          hoursAgo: 1,
        },
        {
          actorId: "system",
          actorType: "system",
          action: "policy.evaluate",
          resource: "policy",
          severity: "warn",
          outcome: "denied",
          details: JSON.stringify({ policyName: "deny-external-after-hours", reason: "After hours restriction" }),
          tags: JSON.stringify(["policy", "denied"]),
          hoursAgo: 2,
        },
        {
          actorId: adminUser.id,
          actorType: "user",
          action: "tool.execute",
          resource: "tool",
          severity: "error",
          outcome: "failure",
          details: JSON.stringify({ toolName: "compute_task", error: "Connection timeout after retries" }),
          tags: JSON.stringify(["execution", "error"]),
          hoursAgo: 4,
        },
        {
          actorId: "system",
          actorType: "system",
          action: "server.health_check",
          resource: "server",
          severity: "info",
          outcome: "success",
          details: JSON.stringify({ serverName: "primary-gateway", status: "healthy", responseTime: 45 }),
          tags: JSON.stringify(["monitoring", "health"]),
          hoursAgo: 6,
        },
        {
          actorId: adminUser.id,
          actorType: "user",
          action: "policy.create",
          resource: "policy",
          severity: "info",
          outcome: "success",
          details: JSON.stringify({ policyName: "business-hours-only", effect: "require_approval" }),
          tags: JSON.stringify(["policy"]),
          hoursAgo: 8,
        },
        {
          actorId: "system",
          actorType: "system",
          action: "security.alert",
          resource: "tool",
          severity: "critical",
          outcome: "denied",
          details: JSON.stringify({ alert: "Unauthorized execution attempt", toolName: "security_scan", blockedBy: "RBAC" }),
          tags: JSON.stringify(["security", "alert", "critical"]),
          hoursAgo: 10,
        },
        {
          actorId: adminUser.id,
          actorType: "user",
          action: "tool.execute",
          resource: "tool",
          severity: "info",
          outcome: "success",
          details: JSON.stringify({ toolName: "metrics_collect", verdict: "allow", duration: 890 }),
          tags: JSON.stringify(["execution"]),
          hoursAgo: 12,
        },
      ];

      await recordAuditBatch(
        auditEntries.map((entry) => ({
          actorId: entry.actorId,
          actorType: entry.actorType as "user" | "system",
          action: entry.action,
          resource: entry.resource,
          severity: entry.severity as "debug" | "info" | "warn" | "error" | "critical",
          outcome: entry.outcome as "success" | "failure" | "denied" | "error",
          details: JSON.parse(entry.details as string) as Record<string, unknown>,
          tags: JSON.parse(entry.tags as string) as string[],
        }))
      );

      // Update createdAt timestamps to reflect hoursAgo
      // (audit logs use default now(), but we want realistic timestamps)
      // We need to update them after creation since Prisma doesn't allow overriding createdAt easily
      const createdLogs = await db.auditLog.findMany({
        orderBy: { createdAt: "desc" },
        take: auditEntries.length,
      });

      for (let i = 0; i < createdLogs.length; i++) {
        const targetTime = new Date(now - auditEntries[i].hoursAgo * 60 * 60 * 1000);
        await db.auditLog.update({
          where: { id: createdLogs[i].id },
          data: { createdAt: targetTime },
        });
      }

      results.push(`Created ${auditEntries.length} sample audit log entries`);
    } else if (existingAuditCount > 0) {
      results.push(`Audit logs already exist (${existingAuditCount} found), skipping`);
    }

    return NextResponse.json({
      success: true,
      data: { results },
      message: "Database seeding completed (idempotent)",
    });
  } catch (error) {
    console.error("[Seed POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to seed database", code: "INTERNAL_ERROR", details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    );
  }
}
