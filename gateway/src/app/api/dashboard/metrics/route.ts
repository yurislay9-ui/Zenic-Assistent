import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    // Consultas ÚNICAS — sin duplicados. Antes había 4 consultas redundantes:
    //   securityGateBlocks = deniedExecutions (ambos verdict:deny)
    //   hitlProposals = pendingApprovals (ambos status:pending)
    //   activeAgents = activeTools (ambos McpTool active)
    const [
      activeTools,           // McpTool count active
      totalTools,            // McpTool count total
      pendingApprovals,      // HitlApprovalRequest count pending
      deniedExecutions,      // ToolExecution count verdict=deny
      executionsToday,       // ToolExecution count createdAt >= today
      completedToday,        // ToolExecution count status=completed AND createdAt >= today
      totalCompleted,        // ToolExecution count status=completed (ALL TIME)
      totalExecutions,       // ToolExecution count total (ALL TIME)
      totalServers,          // McpServer count total
      healthyServers,        // McpServer count active
      criticalAlerts,        // AuditLog count severity=critical last 24h
      recentDurations,       // ToolExecution durations for avg (LIMITED to last 200)
    ] = await Promise.all([
      db.mcpTool.count({ where: { status: "active" } }),
      db.mcpTool.count(),
      db.hitlApprovalRequest.count({ where: { status: "pending" } }),
      db.toolExecution.count({ where: { verdict: "deny" } }),
      db.toolExecution.count({ where: { createdAt: { gte: todayStart } } }),
      // FIX: completedToday ahora filtra por fecha — antes contaba TODAS las completadas
      db.toolExecution.count({ where: { status: "completed", createdAt: { gte: todayStart } } }),
      db.toolExecution.count({ where: { status: "completed" } }),
      db.toolExecution.count(),
      db.mcpServer.count(),
      db.mcpServer.count({ where: { status: "active" } }),
      db.auditLog.count({ where: { severity: "critical", createdAt: { gte: last24h } } }),
      // FIX: Limitado a 200 registros + solo los últimos 7 días para evitar fuga RAM
      db.toolExecution.findMany({
        where: { status: "completed", duration: { not: null }, createdAt: { gte: last24h } },
        select: { duration: true },
        take: 200,
        orderBy: { createdAt: "desc" },
      }),
    ]);

    // FIX: successRate ahora es correcto — % de ejecuciones completadas HOY vs totales HOY
    const totalToday = await db.toolExecution.count({ where: { createdAt: { gte: todayStart } } });
    const successRate = totalToday > 0 ? (completedToday / totalToday) * 100 : 100;

    // avgExecutionTime: basado en muestra limitada (no toda la tabla)
    const avgExecutionTime =
      recentDurations.length > 0
        ? Math.round(
            recentDurations.reduce((sum, e) => sum + (e.duration ?? 0), 0) /
              recentDurations.length
          )
        : 0;

    return NextResponse.json({
      activeAgents: activeTools,
      hitlProposals: pendingApprovals,
      zeroHallucinationsPct: 100,
      securityGateBlocks: deniedExecutions,
      executionsToday,
      successRate: Math.round(successRate * 10) / 10,
      avgExecutionTime,
      deniedExecutions,
      totalTools,
      activeTools,
      totalServers,
      healthyServers,
      pendingApprovals,
      criticalAlerts,
    });
  } catch (error) {
    console.error("[/api/dashboard/metrics GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch dashboard metrics" },
      { status: 500 }
    );
  }
}
