// ─── Zenic-Agents MCP Gateway — Metrics Service ───────────────────────
// Dashboard metrics aggregation — uses Prisma for data queries.

import { db } from "@/lib/db";
import type { DashboardMetrics, ActivityItem } from "../types";

/**
 * Compute dashboard metrics from the database.
 */
export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  const [
    totalTools,
    activeTools,
    totalServers,
    healthyServers,
    executionsToday,
    completedToday,
    failedToday,
    deniedToday,
    pendingApprovals,
    recentExecutions,
  ] = await Promise.all([
    db.mcpTool.count(),
    db.mcpTool.count({ where: { status: "active" } }),
    db.mcpServer.count(),
    db.mcpServer.count({ where: { status: "active" } }),
    db.toolExecution.count({ where: { createdAt: { gte: todayStart } } }),
    db.toolExecution.count({ where: { createdAt: { gte: todayStart }, status: "completed" } }),
    db.toolExecution.count({ where: { createdAt: { gte: todayStart }, status: "failed" } }),
    db.toolExecution.count({ where: { createdAt: { gte: todayStart }, status: "denied" } }),
    db.toolExecution.count({ where: { status: "pending" } }),
    db.toolExecution.findMany({
      where: { createdAt: { gte: todayStart } },
      select: { duration: true },
    }),
  ]);

  const successRate = executionsToday > 0 ? (completedToday / executionsToday) * 100 : 100;
  const avgExecutionTime =
    recentExecutions.length > 0
      ? recentExecutions.reduce((sum, e) => sum + (e.duration ?? 0), 0) / recentExecutions.length
      : 0;

  // Top tools
  const topToolsRaw = await db.toolExecution.groupBy({
    by: ["toolId"],
    where: { createdAt: { gte: todayStart } },
    _count: { id: true },
    orderBy: { _count: { id: "desc" } },
    take: 5,
  });

  const topTools = await Promise.all(
    topToolsRaw.map(async (t) => {
      const tool = await db.mcpTool.findUnique({ where: { id: t.toolId } });
      const total = t._count.id;
      const completed = await db.toolExecution.count({
        where: { toolId: t.toolId, status: "completed", createdAt: { gte: todayStart } },
      });
      return {
        name: tool?.name ?? t.toolId,
        count: total,
        successRate: total > 0 ? (completed / total) * 100 : 0,
      };
    }),
  );

  // Risk distribution
  const allTools = await db.mcpTool.findMany({ select: { riskLevel: true } });
  const riskDistribution = { low: 0, medium: 0, high: 0, critical: 0 } as DashboardMetrics["riskDistribution"];
  for (const t of allTools) {
    const level = (t.riskLevel as keyof typeof riskDistribution) ?? "low";
    if (level in riskDistribution) {
      riskDistribution[level]++;
    }
  }

  // Category distribution
  const categoryDistribution = {
    data: 0, communication: 0, compute: 0, storage: 0,
    external: 0, security: 0, monitoring: 0,
  } as DashboardMetrics["categoryDistribution"];
  for (const t of allTools) {
    // Also count by category — need another query
  }
  const categoryCounts = await db.mcpTool.groupBy({
    by: ["category"],
    _count: { id: true },
  });
  for (const c of categoryCounts) {
    const cat = c.category as keyof typeof categoryDistribution;
    if (cat in categoryDistribution) {
      categoryDistribution[cat] = c._count.id;
    }
  }

  // Executions by hour (last 24h)
  const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const hourlyExecutions = await db.toolExecution.findMany({
    where: { createdAt: { gte: last24h } },
    select: { createdAt: true, status: true },
  });
  const executionsByHour: DashboardMetrics["executionsByHour"] = [];
  for (let h = 0; h < 24; h++) {
    const hourStr = `${h.toString().padStart(2, "0")}:00`;
    const hourEntries = hourlyExecutions.filter((e) => e.createdAt.getHours() === h);
    executionsByHour.push({
      hour: hourStr,
      count: hourEntries.length,
      failures: hourEntries.filter((e) => e.status === "failed" || e.status === "denied").length,
    });
  }

  return {
    totalTools,
    activeTools,
    totalServers,
    healthyServers,
    executionsToday,
    executionsSuccessRate: Math.round(successRate * 10) / 10,
    avgExecutionTime: Math.round(avgExecutionTime),
    deniedExecutions: deniedToday,
    pendingApprovals,
    criticalAlerts: 0,
    topTools,
    executionsByHour,
    riskDistribution,
    categoryDistribution,
  };
}

/**
 * Get the activity feed for the dashboard.
 */
export async function getActivityFeed(limit = 20): Promise<ActivityItem[]> {
  const logs = await db.auditLog.findMany({
    where: {
      severity: { in: ["info", "warn", "error", "critical"] },
    },
    orderBy: { createdAt: "desc" },
    take: limit,
  });

  return logs.map((log) => ({
    id: log.id,
    type: mapActionToType(log.action),
    title: formatActionTitle(log.action, log.resource),
    description: `${log.outcome}: ${log.action} on ${log.resource}${log.resourceId ? ` (${log.resourceId})` : ""}`,
    timestamp: log.createdAt.toISOString(),
    severity: log.severity as ActivityItem["severity"],
    actorName: log.actorId ?? "system",
    resourceName: log.resourceName,
  }));
}

function mapActionToType(action: string): ActivityItem["type"] {
  if (action.includes("execute") || action.includes("gateway")) return "execution";
  if (action.includes("approve") || action.includes("deny")) return "approval";
  if (action.includes("policy")) return "policy_change";
  if (action.includes("role") || action.includes("assign") || action.includes("revoke")) return "role_change";
  return "alert";
}

function formatActionTitle(action: string, resource: string): string {
  return `${action.replace(/\./g, " → ")} ${resource}`;
}
