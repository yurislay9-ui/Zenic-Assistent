// ─── SNA Alerts — Paginación cursor (keyset) ────────────────────────
// FIX: Antes cargaba TODOS los auditLog de las últimas 24h sin límite.
// Ahora: máximo 200 por request, paginación cursor O(1).
// Si el frontend no manda ?cursor=, funciona igual (primera página de 50).
// INVARIANT 3 protegida: RAM acotada sin importar el volumen de alertas.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { parsePagination, cursorWhere } from "@/lib/api-utils";

export async function GET(request: NextRequest) {
  try {
    const { limit, cursor } = parsePagination(request);
    const now = new Date();
    const last24h = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    const alerts = await db.auditLog.findMany({
      where: {
        severity: { in: ["warn", "error", "critical"] },
        createdAt: { gte: last24h },
        ...cursorWhere(cursor),
      },
      orderBy: { id: "desc" }, // keyset pagination usa id, no createdAt
      take: limit + 1, // +1 para saber si hay más páginas
    });

    // Si hay más de `limit` resultados, hay página siguiente
    const hasMore = alerts.length > limit;
    const items = hasMore ? alerts.slice(0, limit) : alerts;
    const nextCursor = hasMore ? items[items.length - 1].id : undefined;

    const formatted = items.map((a) => {
      let details = "";
      try {
        const parsed = JSON.parse(a.details);
        details =
          parsed.alert ??
          parsed.reason ??
          parsed.error ??
          parsed.message ??
          a.details;
      } catch {
        details = a.details;
      }

      return {
        id: a.id,
        severity: a.severity,
        action: a.action,
        resourceName: a.resourceName ?? a.resource,
        details,
        createdAt: a.createdAt.toISOString(),
      };
    });

    return NextResponse.json({
      alerts: formatted,
      pagination: {
        nextCursor,
        hasMore,
        limit,
      },
    });
  } catch (error) {
    console.error("[/api/dashboard/sna-alerts GET]", error);
    return NextResponse.json(
      { error: "Failed to fetch SNA alerts" },
      { status: 500 }
    );
  }
}
