// ─── Zenic-Agents v3 — RBAC Assign Role (Refactorizado FASE 9) ────────
// CAMBIOS:
// - Autenticación obligatoria (requireAuthAndPermission)
// - Audit logging de la asignación
// - Error genérico al cliente, detalles solo en server log

import { NextRequest, NextResponse } from "next/server";
import { assignRole } from "@/lib/mcp-gateway/services/rbac-service";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import { requireAuthAndPermission } from "@/lib/rbac-auth";

export async function POST(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "role", "write");
  if (authResult instanceof NextResponse) return authResult;
  const { user } = authResult;

  try {
    const body = await request.json();
    const { userId, roleId, expiresAt } = body as {
      userId: string;
      roleId: string;
      expiresAt?: string;
    };

    if (!userId || !roleId) {
      return NextResponse.json(
        { success: false, error: "userId y roleId son requeridos", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Verify role exists
    const { db } = await import("@/lib/db");
    const role = await db.role.findUnique({ where: { id: roleId } });
    if (!role) {
      return NextResponse.json(
        { success: false, error: "Rol no encontrado", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    // Verify target user exists
    const targetUser = await db.user.findUnique({ where: { id: userId } });
    if (!targetUser) {
      return NextResponse.json(
        { success: false, error: "Usuario no encontrado", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    // Validate expiry date
    const expiresAtDate = expiresAt ? new Date(expiresAt) : undefined;
    if (expiresAtDate && expiresAtDate <= new Date()) {
      return NextResponse.json(
        { success: false, error: "expiresAt debe ser una fecha futura", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Assign role (handles expired re-assignment internally)
    const assignment = await assignRole(userId, roleId, user.userId, expiresAtDate);

    // Audit logging
    await recordAudit({
      actorId: user.userId,
      actorType: "user",
      action: "role.assign",
      resource: "role",
      resourceId: roleId,
      resourceName: role.name,
      severity: "info",
      details: {
        targetUserId: userId,
        targetUserName: targetUser.name,
        roleName: role.name,
        expiresAt: expiresAtDate?.toISOString(),
      },
    });

    return NextResponse.json({
      success: true,
      data: assignment,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("DUPLICATE:")) {
      return NextResponse.json(
        { success: false, error: "Rol ya asignado a este usuario", code: "DUPLICATE" },
        { status: 409 },
      );
    }
    console.error("[RBAC Assign POST]", error);
    return NextResponse.json(
      { success: false, error: "Error al asignar rol", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
