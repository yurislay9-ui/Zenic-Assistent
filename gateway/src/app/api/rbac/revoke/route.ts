// ─── Zenic-Agents v3 — RBAC Revoke Role (Refactorizado FASE 9) ────────
// CAMBIOS:
// - Autenticación obligatoria (requireAuthAndPermission)
// - Audit logging de la revocación
// - Error genérico al cliente

import { NextRequest, NextResponse } from "next/server";
import { revokeRole } from "@/lib/mcp-gateway/services/rbac-service";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import { requireAuthAndPermission } from "@/lib/rbac-auth";

export async function POST(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "role", "delete");
  if (authResult instanceof NextResponse) return authResult;
  const { user } = authResult;

  try {
    const body = await request.json();
    const { userId, roleId } = body as {
      userId: string;
      roleId: string;
    };

    if (!userId || !roleId) {
      return NextResponse.json(
        { success: false, error: "userId y roleId son requeridos", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Check if assignment exists
    const { db } = await import("@/lib/db");
    const existing = await db.userRole.findUnique({
      where: { userId_roleId: { userId, roleId } },
      include: { role: true },
    });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Asignación de rol no encontrada", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    // Prevent revoking system roles from self (self-demotion protection)
    if (existing.role.isSystem && userId === user.userId) {
      return NextResponse.json(
        { success: false, error: "No puede revocar sus propios roles de sistema", code: "FORBIDDEN" },
        { status: 403 },
      );
    }

    await revokeRole(userId, roleId, user.userId);

    // Audit logging
    await recordAudit({
      actorId: user.userId,
      actorType: "user",
      action: "role.revoke",
      resource: "role",
      resourceId: roleId,
      resourceName: existing.role.name,
      severity: "warn",
      details: {
        targetUserId: userId,
        roleName: existing.role.name,
      },
    });

    return NextResponse.json({
      success: true,
      data: { userId, roleId },
      message: "Rol revocado exitosamente",
    });
  } catch (error) {
    console.error("[RBAC Revoke POST]", error);
    return NextResponse.json(
      { success: false, error: "Error al revocar rol", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
