import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function GET() {
  try {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const last7d = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const last30d = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

    // FIX: Todas las consultas en paralelo con Promise.all.
    // Antes: N+1 query — 14 consultas en un bucle for.
    // Ahora: 1 sola tanda paralela + weekly trend con 7 queries paralelas.
    const [
      completedToday,
      deniedToday,
      completed7d,
      completed30d,
      totalExecutions,
      securityBlocksTotal,
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
      db.toolExecution.count({ where: { verdict: "deny" } }),
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

    // FIX: Weekly trend con 7 queries EN PARALELO (antes era un bucle secuencial N+1)
    const weeklyPromises = Array.from({ length: 7 }, (_, i) => {
      const d = 6 - i;
      const dayStart = new Date(now);
      dayStart.setDate(dayStart.getDate() - d);
      dayStart.setHours(0, 0, 0, 0);
      const dayEnd = new Date(dayStart);
      dayEnd.setDate(dayEnd.getDate() + 1);

      return Promise.all([
        dayStart,
        db.toolExecution.count({
          where: { status: "completed", createdAt: { gte: dayStart, lt: dayEnd } },
        }),
        db.toolExecution.count({
          where: { verdict: "deny", createdAt: { gte: dayStart, lt: dayEnd } },
        }),
      ]);
    });

    const dayNames = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];
    const weeklyResults = await Promise.all(weeklyPromises);
    const weeklyTrend = weeklyResults.map(([dayStart, dayCompleted, dayDenied]) => ({
      day: dayNames[(dayStart as Date).getDay()],
      exitosas: dayCompleted as number,
      bloqueadas: dayDenied as number,
    }));

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
      planLimit: "1000/1000",
    });
  } catch (error) {
    console.error("[/api/dashboard/roi GET]", error);
    return NextResponse.json(
      { error: "Error al calcular valor generado" },
      { status: 500 }
    );
  }
}
