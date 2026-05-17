// ─── Zenic-Agents v3 — RBAC Permissions List (Refactorizado FASE 9) ──
// CAMBIOS:
// - Autenticación obligatoria
// - Eliminada doble-query innecesaria (bug de rendimiento)
// - Paginación consistente siempre

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requireAuthAndPermission } from "@/lib/rbac-auth";
import type { PaginatedResponse } from "@/lib/mcp-gateway/types";

export async function GET(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "permission", "read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const resource = searchParams.get("resource") || undefined;
    const action = searchParams.get("action") || undefined;
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 50));

    const where: Record<string, unknown> = {};
    if (resource) where.resource = resource;
    if (action) where.action = action;

    // Single unified query — siempre paginada
    const [permissions, total] = await Promise.all([
      db.permission.findMany({
        where,
        orderBy: [{ resource: "asc" }, { action: "asc" }],
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.permission.count({ where }),
    ]);

    const response: PaginatedResponse<typeof permissions[number]> = {
      success: true,
      data: permissions,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[RBAC Permissions GET]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener permisos", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
