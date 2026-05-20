import { db } from "@/lib/db";
import { createHash } from "crypto";

/** Generate a SHA-256 content hash */
function sha256(content: string): string {
  return createHash("sha256").update(content).digest("hex");
}

/**
 * Seed HITL approval requests, audit logs, and Merkle-chain audit trail.
 * Sections 7–9 of the original monolithic seed route.
 */
export async function seedPoliciesAndAudit(adminUserId: string | undefined): Promise<string[]> {
  const results: string[] = [];

  // ─── 7. Seed 5 Pending HitlApprovalRequests (Memory Proposals) ───
  const existingHitlCount = await db.hitlApprovalRequest.count();
  if (existingHitlCount === 0 && adminUserId) {
    const hitlData = [
      {
        requestId: "mp-001",
        title: "Schema Drift: Column 'monto_neto' missing",
        description: "Map 'monto_neto' to 'subtotal_neto' — detected drift in ERP→Analytics schema pipeline",
        type: "action_approval",
        status: "pending",
        priority: "medium",
        requesterId: adminUserId,
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
        requesterId: adminUserId,
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
        requesterId: adminUserId,
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
        requesterId: adminUserId,
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
        requesterId: adminUserId,
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
  if (existingAuditCount === 0 && adminUserId) {
    const now = Date.now();
    const auditEntries = [
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "weather_lookup", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "weather_lookup", verdict: "allow", duration: 450 }), tags: JSON.stringify(["execution"]), hoursAgo: 0.5 },
      { actorId: "system", actorType: "system", action: "policy.evaluate", resource: "policy", resourceName: "business-hours-only", severity: "info", outcome: "success", details: JSON.stringify({ policyName: "business-hours-only", verdict: "allow" }), tags: JSON.stringify(["policy"]), hoursAgo: 1 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "db_query", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "db_query", verdict: "allow", duration: 1200 }), tags: JSON.stringify(["execution"]), hoursAgo: 1.5 },
      { actorId: "system", actorType: "system", action: "policy.evaluate", resource: "policy", resourceName: "deny-external-after-hours", severity: "warn", outcome: "denied", details: JSON.stringify({ policyName: "deny-external-after-hours", reason: "After hours restriction" }), tags: JSON.stringify(["policy", "denied"]), hoursAgo: 2 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "file_read", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "file_read", verdict: "allow", duration: 230 }), tags: JSON.stringify(["execution"]), hoursAgo: 3 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "compute_task", severity: "error", outcome: "failure", details: JSON.stringify({ toolName: "compute_task", error: "Connection timeout after retries", duration: 5000 }), tags: JSON.stringify(["execution", "error"]), hoursAgo: 4 },
      { actorId: "system", actorType: "system", action: "security.alert", resource: "tool", resourceName: "security_scan", severity: "critical", outcome: "denied", details: JSON.stringify({ alert: "Unauthorized execution attempt", toolName: "security_scan", blockedBy: "RBAC" }), tags: JSON.stringify(["security", "alert", "critical"]), hoursAgo: 5 },
      { actorId: "system", actorType: "system", action: "server.health_check", resource: "server", resourceName: "primary-gateway", severity: "info", outcome: "success", details: JSON.stringify({ serverName: "primary-gateway", status: "healthy", responseTime: 45 }), tags: JSON.stringify(["monitoring", "health"]), hoursAgo: 6 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "metrics_collect", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "metrics_collect", verdict: "allow", duration: 890 }), tags: JSON.stringify(["execution"]), hoursAgo: 8 },
      { actorId: adminUserId, actorType: "user", action: "policy.create", resource: "policy", resourceName: "business-hours-only", severity: "info", outcome: "success", details: JSON.stringify({ policyName: "business-hours-only", effect: "require_approval" }), tags: JSON.stringify(["policy"]), hoursAgo: 10 },
      { actorId: "system", actorType: "system", action: "tool.execute", resource: "tool", resourceName: "email_send", severity: "warn", outcome: "denied", details: JSON.stringify({ toolName: "email_send", verdict: "deny", reason: "Rate limit exceeded" }), tags: JSON.stringify(["execution", "rate-limit"]), hoursAgo: 12 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "webhook_dispatch", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "webhook_dispatch", verdict: "allow", duration: 320 }), tags: JSON.stringify(["execution"]), hoursAgo: 14 },
      { actorId: "system", actorType: "system", action: "resource.low_stock", resource: "inventory", resourceName: "Inventory", severity: "warn", outcome: "success", details: JSON.stringify({ alert: "Low stock (5 items)", sku: "WH-0042" }), tags: JSON.stringify(["inventory", "alert"]), hoursAgo: 16 },
      { actorId: adminUserId, actorType: "user", action: "role.assign", resource: "role", resourceName: "superadmin", severity: "info", outcome: "success", details: JSON.stringify({ targetUserId: adminUserId, role: "superadmin" }), tags: JSON.stringify(["rbac"]), hoursAgo: 18 },
      { actorId: "system", actorType: "system", action: "server.health_check", resource: "server", resourceName: "notification-hub", severity: "error", outcome: "failure", details: JSON.stringify({ serverName: "notification-hub", status: "unhealthy", error: "SMTP timeout" }), tags: JSON.stringify(["monitoring", "health", "error"]), hoursAgo: 20 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "inventory_check", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "inventory_check", verdict: "allow", duration: 150 }), tags: JSON.stringify(["execution"]), hoursAgo: 22 },
      { actorId: "system", actorType: "system", action: "security.alert", resource: "tool", resourceName: "compute_task", severity: "critical", outcome: "denied", details: JSON.stringify({ alert: "GPU resource abuse attempt", toolName: "compute_task", blockedBy: "Policy Engine" }), tags: JSON.stringify(["security", "alert", "critical"]), hoursAgo: 23 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "schema_mapper", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "schema_mapper", verdict: "conditional", duration: 1200 }), tags: JSON.stringify(["execution"]), hoursAgo: 30 },
      { actorId: "system", actorType: "system", action: "policy.evaluate", resource: "policy", resourceName: "rate-limit-operators", severity: "warn", outcome: "success", details: JSON.stringify({ policyName: "rate-limit-operators", remainingQuota: 3, window: "1h" }), tags: JSON.stringify(["policy", "quota"]), hoursAgo: 36 },
      { actorId: adminUserId, actorType: "user", action: "tool.execute", resource: "tool", resourceName: "weather_lookup", severity: "info", outcome: "success", details: JSON.stringify({ toolName: "weather_lookup", verdict: "allow", duration: 380 }), tags: JSON.stringify(["execution"]), hoursAgo: 40 },
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
  if (existingAuditTrailCount === 0 && adminUserId) {
    const hitlRequests = await db.hitlApprovalRequest.findMany({ take: 5 });
    if (hitlRequests.length > 0) {
      const auditEvents = [
        { requestId: hitlRequests[0].requestId, eventType: "created", actorId: adminUserId, actorName: "Memory Engine", details: JSON.stringify({ proposal: "Schema Drift detected" }) },
        { requestId: hitlRequests[1].requestId, eventType: "created", actorId: adminUserId, actorName: "Memory Engine", details: JSON.stringify({ proposal: "Intent Routing update" }) },
        { requestId: hitlRequests[0].requestId, eventType: "approved", actorId: adminUserId, actorName: "Admin User", details: JSON.stringify({ approvedBy: "Admin User", comment: "Looks good, mapping is correct" }) },
        { requestId: hitlRequests[2].requestId, eventType: "created", actorId: adminUserId, actorName: "Memory Engine", details: JSON.stringify({ proposal: "Policy Refinement request" }) },
        { requestId: hitlRequests[1].requestId, eventType: "approved", actorId: adminUserId, actorName: "Admin User", details: JSON.stringify({ approvedBy: "Admin User", comment: "Routing makes sense based on usage data" }) },
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

  return results;
}
