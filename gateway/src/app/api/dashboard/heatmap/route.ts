// ─── Verdict Heatmap — Agregación SQL-side ───────────────────────────
// FIX: Antes cargaba TODAS las ejecuciones de 24h en memoria y filtraba
// con 24 pasadas O(n) en JavaScript. Ahora: 1 query SQL con GROUP BY,
// exactamente 24 filas (o menos), RAM constante.
// INVARIANT 3 protegida: RAM no crece con el volumen de datos.

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

interface HeatmapRow {
  hour: number;
  allowed: number;
  confirmed: number;
  blocked: number;
}

export async function GET() {
  try {
    const now = new Date();
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    // ── Agregación SQL-side ──────────────────────────────────────────
    // Una sola query. SQLite agrupa por hora y cuenta por verdict.
    // Antes: findMany sin take + 24 pasadas O(n) en JS.
    // Ahora: 1 query, máximo 24 filas, cero objetos innecesarios en memoria.
    const rows = await db.$queryRaw<HeatmapRow[]>`
      SELECT
        CAST(strftime('%H', "createdAt") AS INTEGER) AS hour,
        SUM(CASE WHEN "verdict" = 'allow' AND "status" = 'completed' THEN 1 ELSE 0 END) AS allowed,
        SUM(CASE WHEN "verdict" = 'conditional' OR ("verdict" = 'allow' AND "status" = 'approved') THEN 1 ELSE 0 END) AS confirmed,
        SUM(CASE WHEN "verdict" = 'deny' THEN 1 ELSE 0 END) AS blocked
      FROM "tool_executions"
      WHERE "createdAt" >= ${last24h}
        AND "verdict" IS NOT NULL
      GROUP BY strftime('%H', "createdAt")
      ORDER BY hour ASC
    `;

    // Llenar las 24 horas (las que no tienen datos quedan en 0)
    const resultMap = new Map(rows.map((r) => [r.hour, r]));

    const segments = Array.from({ length: 24 }, (_, h) => {
      const row = resultMap.get(h);
      return {
        hour: `${h.toString().padStart(2, "0")}:00`,
        allowed: row?.allowed ?? 0,
        confirmed: row?.confirmed ?? 0,
        blocked: row?.blocked ?? 0,
      };
    });

    return NextResponse.json({ segments });
  } catch (error) {
    console.error("[/api/dashboard/heatmap GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch verdict heatmap" },
      { status: 500 }
    );
  }
}
