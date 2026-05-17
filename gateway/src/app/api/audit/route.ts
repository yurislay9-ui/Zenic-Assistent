// ─── Zenic-Agents v3 — Audit Log Query (Refactorizado FASE 9) ────────
// CAMBIOS:
// - Autenticación obligatoria (requireAuthAndPermission con audit:read)
// - safeJsonParse centralizado desde utils
// - Keyset pagination (cursor-based) para eficiencia con SQLite
// - Búsqueda con OR limitada a 3 campos (no 5) para reducir carga
// - Límite máximo de resultados reducido a 50 por página

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requireAuthAndPermission } from "@/lib/rbac-auth";
import { safeJsonParse } from "@/lib/utils";
import type { AuditQuery } from "@/lib/mcp-gateway/types";

export async function GET(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "audit", "read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);

    const query: AuditQuery = {
      actorId: searchParams.get("actorId") || undefined,
      action: searchParams.get("action") || undefined,
      resource: searchParams.get("resource") || undefined,
      severity: (searchParams.get("severity") as AuditQuery["severity"]) || undefined,
      outcome: (searchParams.get("outcome") as AuditQuery["outcome"]) || undefined,
      startDate: searchParams.get("startDate") || undefined,
      endDate: searchParams.get("endDate") || undefined,
      search: searchParams.get("search") || undefined,
    };

    const pageSize = Math.min(50, Math.max(1, Number(searchParams.get("pageSize")) || 20));
    const cursor = searchParams.get("cursor") || undefined;

    // Build where clause
    const where: {
      id?: { gt: string };
      actorId?: string;
      action?: { contains: string };
      resource?: string;
      severity?: string;
      outcome?: string;
      createdAt?: { gte?: Date; lte?: Date };
      OR?: Array<Record<string, unknown>>;
    } = {};

    // Keyset pagination: si hay cursor, filtrar por id > cursor
    if (cursor) {
      where.id = { gt: cursor };
    }

    if (query.actorId) where.actorId = query.actorId;
    if (query.action) where.action = { contains: query.action };
    if (query.resource) where.resource = query.resource;
    if (query.severity) where.severity = query.severity;
    if (query.outcome) where.outcome = query.outcome;

    if (query.startDate || query.endDate) {
      where.createdAt = {};
      if (query.startDate) where.createdAt.gte = new Date(query.startDate);
      if (query.endDate) where.createdAt.lte = new Date(query.endDate);
    }

    // Search limitado a 3 campos críticos (no 5)
    if (query.search) {
      where.OR = [
        { action: { contains: query.search } },
        { resource: { contains: query.search } },
        { resourceName: { contains: query.search } },
      ];
    }

    const [logs, total] = await Promise.all([
      db.auditLog.findMany({
        where,
        orderBy: cursor ? { id: "asc" } : { createdAt: "desc" },
        take: pageSize + 1, // +1 para determinar si hay página siguiente
      }),
      db.auditLog.count({ where }),
    ]);

    // Determinar si hay página siguiente
    const hasNextPage = logs.length > pageSize;
    const data = hasNextPage ? logs.slice(0, pageSize) : logs;
    const nextCursor = hasNextPage ? data[data.length - 1].id : null;

    // Parse JSON fields
    const parsedData = data.map((log) => ({
      ...log,
      details: safeJsonParse(log.details),
      tags: safeJsonParse(log.tags),
    }));

    return NextResponse.json({
      success: true,
      data: parsedData,
      total,
      pageSize,
      nextCursor,
      hasMore: hasNextPage,
    });
  } catch (error) {
    console.error("[Audit GET]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener logs de auditoría", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
