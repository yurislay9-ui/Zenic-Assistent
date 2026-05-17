// ─── Zenic-Agents v3 — Phase 1 Policies (DEPRECATED — Refactorizado FASE 9)
// DEPRECATED: Use /api/v1/policies for declarative policy management
// This route is kept for backward compatibility with Phase 1 MCP Gateway.
//
// CAMBIOS FASE 9:
// - POST y PUT retornan 410 Gone (deprecated mutations deshabilitadas)
// - GET mantiene funcionalidad para lectura de AccessPolicy legacy
// - Autenticación obligatoria en GET
// - safeJsonParse centralizado desde utils

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { requireAuthAndPermission } from "@/lib/rbac-auth";
import { safeJsonParse } from "@/lib/utils";
import type { PaginatedResponse } from "@/lib/mcp-gateway/types";

/** Add deprecation headers to response */
function withDeprecation(response: NextResponse): NextResponse {
  response.headers.set("Deprecation", "true");
  response.headers.set(
    "Link",
    '</api/v1/policies>; rel="successor-version"',
  );
  response.headers.set(
    "X-Deprecated-Notice",
    "This endpoint is deprecated. Use /api/v1/policies for declarative policy management.",
  );
  return response;
}

export async function GET(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "policy", "read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20));

    const [policies, total] = await Promise.all([
      db.accessPolicy.findMany({
        include: {
          toolAccessPolicies: {
            include: { tool: { select: { id: true, name: true, displayName: true } } },
          },
        },
        orderBy: { priority: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.accessPolicy.count(),
    ]);

    const data = policies.map((policy) => ({
      ...policy,
      conditions: safeJsonParse(policy.conditions),
      timeWindow: policy.timeWindow ? safeJsonParse(policy.timeWindow) : null,
      quota: policy.quota ? safeJsonParse(policy.quota) : null,
      tools: policy.toolAccessPolicies.map((tap) => tap.tool),
      toolAccessPolicies: undefined,
    }));

    const response: PaginatedResponse<typeof data[number]> = {
      success: true,
      data,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    };

    return withDeprecation(NextResponse.json(response));
  } catch (error) {
    console.error("[Policies GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch policies", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// ─── Mutaciones DEPRECATED: retornar 410 Gone ─────────────────────────
// Las operaciones de escritura en esta ruta legacy están deshabilitadas.
// Use /api/v1/policies para gestión declarativa de políticas.

export async function POST() {
  return withDeprecation(NextResponse.json(
    {
      success: false,
      error: "This endpoint is deprecated. Use POST /api/v1/policies for policy creation.",
      code: "GONE",
    },
    { status: 410 },
  ));
}
