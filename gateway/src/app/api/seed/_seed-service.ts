// ─── Seed Service ──────────────────────────────────────────────────────
// Business logic for database seeding. Extracted from route.ts for modularity.

import { db } from "@/lib/db";
import { createHash } from "crypto";
import {
  ROLE_DEFS,
  PERMISSION_DEFS,
  getServerDefs,
  SERIES_DEFS,
} from "./_seed-data-core";
import {
  getToolDefs,
  getHitlData,
  getAuditEntries,
} from "./_seed-data-content";

/** Generate a SHA-256 content hash */
function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

/** Run the full idempotent seed process */
export async function runSeed(): Promise<{ results: string[] }> {
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
  for (const rd of ROLE_DEFS) {
    const existing = await db.role.findUnique({ where: { name: rd.name } });
    if (!existing) {
      await db.role.create({ data: rd });
    }
  }
  results.push("Roles ensured (4 roles)");

  // ─── 3. Seed 18 Permissions ──────────────────────────────────────
  const existingPermCount = await db.permission.count();
  if (existingPermCount === 0) {
    await db.permission.createMany({ data: PERMISSION_DEFS });
    results.push(`Created ${PERMISSION_DEFS.length} permissions`);
  } else {
    results.push(`Permissions already exist (${existingPermCount} found), skipping`);
  }

  // ─── 4. Seed 5 MCP Servers ───────────────────────────────────────
  const serverDefs = getServerDefs();
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
  const toolDefs = getToolDefs(serverIds);
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

    const statusMix: Array<{ status: string; verdict: string | null; weight: number }> = [
      { status: "completed", verdict: "allow", weight: 35 },
      { status: "completed", verdict: "conditional", weight: 5 },
      { status: "failed", verdict: "allow", weight: 3 },
      { status: "denied", verdict: "deny", weight: 4 },
      { status: "timeout", verdict: "allow", weight: 2 },
      { status: "pending", verdict: null, weight: 1 },
    ];

    for (let i = 0; i < 50; i++) {
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
        hoursAgo: Math.random() * 48,
      });
    }

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
    const hitlData = getHitlData(adminUser.id);
    for (const h of hitlData) {
      await db.hitlApprovalRequest.create({ data: h as never });
    }
    results.push(`Created 5 pending HITL approval requests (memory proposals)`);
  } else if (existingHitlCount > 0) {
    results.push(`HITL approval requests already exist (${existingHitlCount} found), skipping`);
  }

  // ─── 8. Seed 20 AuditLog Entries ─────────────────────────────────
  const existingAuditCount = await db.auditLog.count();
  if (existingAuditCount === 0 && adminUser) {
    const now = Date.now();
    const auditEntries = getAuditEntries(adminUser.id);

    await db.auditLog.createMany({
      data: auditEntries.map((entry) => ({
        actorId: entry.actorType === "user" ? (entry.actorId as string) : null,
        actorType: entry.actorType as string,
        action: entry.action as string,
        resource: entry.resource as string,
        resourceName: entry.resourceName as string,
        severity: entry.severity as string,
        outcome: entry.outcome as string,
        details: entry.details as string,
        tags: entry.tags as string,
        createdAt: new Date(now - (entry.hoursAgo as number) * 60 * 60 * 1000),
      })),
    });
    results.push(`Created 20 audit log entries`);
  } else if (existingAuditCount > 0) {
    results.push(`Audit logs already exist (${existingAuditCount} found), skipping`);
  }

  // ─── 9. Seed 5 HitlApprovalAudit Entries with Merkle Chain ───────
  const existingAuditTrailCount = await db.hitlApprovalAudit.count();
  if (existingAuditTrailCount === 0 && adminUser) {
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
            timestamp: new Date(now - (auditEvents.length - i) * 30 * 60 * 1000),
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
    const now = Date.now();

    for (const sd of SERIES_DEFS) {
      const series = await db.metricSeries.create({ data: sd });

      const points = [];
      for (let h = 0; h < 24; h++) {
        let value: number;
        switch (sd.unit) {
          case "percent":
            value = Math.round((Math.random() * 5 + 0.5) * 100) / 100;
            break;
          case "ms":
            value = Math.round(Math.random() * 100 + 20);
            break;
          case "usd":
            value = Math.round((Math.random() * 0.5 + 0.05) * 1000) / 1000;
            break;
          case "count":
          default:
            value = Math.round(Math.random() * 50 + 5);
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

  return { results };
}
