// ─── Zenic-Agents v3 — RBAC Permission Check (Refactorizado FASE 9) ──
// CAMBIOS:
// - Autenticación obligatoria
// - Respuesta NO expone constraints internos (information disclosure)
// - Audit logging de checks denegados (security monitoring)

import { NextRequest, NextResponse } from "next/server";
import { checkPermission } from "@/lib/mcp-gateway/services/rbac-service";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import { requireAuth } from "@/lib/rbac-auth";
import type { PermissionCheck, PermissionCheckResult } from "@/lib/mcp-gateway/types";

export async function POST(request: NextRequest) {
  // ─── Auth Check (solo requiere autenticación, no permisos específicos) ──
  const authResult = await requireAuth(request);
  if (authResult instanceof NextResponse) return authResult;
  // authResult es AuthenticatedUser { userId, primaryRole }
  const authenticatedUser = authResult;

  try {
    const body = await request.json();
    const { resource, action, context } = body as Omit<PermissionCheck, "userId"> & {
      userId?: string;
    };

    if (!resource || !action) {
      return NextResponse.json(
        { success: false, error: "resource y action son requeridos", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Siempre checkear permisos para el usuario autenticado
    // (no permitir especificar userId arbitrario)
    const result: PermissionCheckResult = await checkPermission({
      userId: authenticatedUser.userId,
      resource,
      action,
      context,
    });

    // Audit logging solo para checks DENEGADOS (security monitoring)
    if (!result.allowed) {
      await recordAudit({
        actorId: authenticatedUser.userId,
        actorType: "user",
        action: "permission.check.denied",
        resource,
        severity: "info",
        outcome: "denied",
        details: {
          action,
          reason: result.reason,
          matchedPolicies: result.matchedPolicies,
        },
      });
    }

    // ─── Sanitizar respuesta: NO exponer constraints internos ────────
    const sanitizedResult: PermissionCheckResult = {
      allowed: result.allowed,
      reason: result.allowed ? "Permission granted" : "Permission denied",
      matchedPolicies: result.matchedPolicies,
      // constraints intencionalmente OMITIDO — información interna
    };

    return NextResponse.json({
      success: true,
      data: sanitizedResult,
    });
  } catch (error) {
    console.error("[RBAC Check POST]", error);
    return NextResponse.json(
      { success: false, error: "Error al verificar permisos", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
