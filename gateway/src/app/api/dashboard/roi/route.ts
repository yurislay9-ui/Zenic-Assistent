import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const last7d = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const last30d = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

    // Get execution data for ROI calculations
    const [
      completedToday,
      deniedToday,
      completed7d,
      completed30d,
      totalExecutions,
    ] = await Promise.all([
      db.toolExecution.count({
        where: { status: "completed", createdAt: { gte: todayStart } },
      }),
      db.toolExecution.count({
        where: { verdict: "deny", createdAt: { gte: todayStart } },
      }),
      db.toolExecution.count({
        where: { status: "completed", createdAt: { gte: last7d } },
      }),
      db.toolExecution.count({
        where: { status: "completed", createdAt: { gte: last30d } },
      }),
      db.toolExecution.count(),
    ]);

    // Estimate value: each automated action saves ~15 min of manual work
    const minutesSavedToday = completedToday * 15;
    const hoursSavedToday = Math.round((minutesSavedToday / 60) * 10) / 10;
    const hoursSaved7d = Math.round((completed7d * 15 / 60) * 10) / 10;
    const hoursSaved30d = Math.round((completed30d * 15 / 60) * 10) / 10;

    // Estimate monetary value at $25/hr average
    const valueToday = Math.round(hoursSavedToday * 25);
    const value7d = Math.round(hoursSaved7d * 25);
    const value30d = Math.round(hoursSaved30d * 25);

    // Actions blocked (security value)
    const securityBlocksTotal = await db.toolExecution.count({
      where: { verdict: "deny" },
    });

    // Weekly trend (last 7 days)
    const weeklyTrend: Array<{ day: string; exitosas: number; bloqueadas: number }> = [];
    for (let d = 6; d >= 0; d--) {
      const dayStart = new Date(now);
      dayStart.setDate(dayStart.getDate() - d);
      dayStart.setHours(0, 0, 0, 0);
      const dayEnd = new Date(dayStart);
      dayEnd.setDate(dayEnd.getDate() + 1);

      const dayCompleted = await db.toolExecution.count({
        where: { status: "completed", createdAt: { gte: dayStart, lt: dayEnd } },
      });
      const dayDenied = await db.toolExecution.count({
        where: { verdict: "deny", createdAt: { gte: dayStart, lt: dayEnd } },
      });

      const dayNames = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
      weeklyTrend.push({
        day: dayNames[dayStart.getDay()],
        exitosas: dayCompleted,
        bloqueadas: dayDenied,
      });
    }

    return NextResponse.json({
      valueToday,
      value7d,
      value30d,
      hoursSavedToday,
      hoursSaved7d,
      hoursSaved30d,
      actionsCompletedToday: completedToday,
      actionsDeniedToday: deniedToday,
      securityBlocksTotal,
      totalAutomations: totalExecutions,
      weeklyTrend,
      planLimit: "1000/1000", // Business plan example
    });
  } catch (error) {
    console.error("[/api/dashboard/roi GET]", error);
    return NextResponse.json(
      { error: "Error al calcular valor generado" },
      { status: 500 }
    );
  }
}
