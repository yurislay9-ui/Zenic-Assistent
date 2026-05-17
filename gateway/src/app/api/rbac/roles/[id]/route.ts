// ─── Zenic-Agents v3 — RBAC Role by ID (Refactorizado FASE 9) ────────
// CAMBIOS:
// - Autenticación obligatoria en todos los métodos
// - PUT requiere role:write, DELETE requiere role:delete
// - PUT: permission replacement envuelto en $transaction
// - DELETE: previene eliminación de roles con usuarios asignados
// - Audit logging con userId real (no hardcoded "api")

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import { requireAuthAndPermission } from "@/lib/rbac-auth";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "role", "read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { id } = await params;

    const role = await db.role.findUnique({
      where: { id },
      include: {
        permissions: {
          include: { permission: true },
        },
      },
    });

    if (!role) {
      return NextResponse.json(
        { success: false, error: "Rol no encontrado", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: {
        ...role,
        permissions: role.permissions.map((rp) => rp.permission),
      },
    });
  } catch (error) {
    console.error("[RBAC Role GET]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener rol", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "role", "write");
  if (authResult instanceof NextResponse) return authResult;
  const { user } = authResult;

  try {
    const { id } = await params;

    const existing = await db.role.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Rol no encontrado", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    // Prevent modifying system roles
    if (existing.isSystem) {
      return NextResponse.json(
        { success: false, error: "Los roles de sistema no pueden ser modificados", code: "FORBIDDEN" },
        { status: 403 },
      );
    }

    const body = await request.json();
    const { name, displayName, description, color, priority, permissionIds } = body;

    // ─── Transaction: update fields + replace permissions atomically ──
    const updatedRole = await db.$transaction(async (tx) => {
      // Update role fields
      const updated = await tx.role.update({
        where: { id },
        data: {
          ...(name !== undefined && { name }),
          ...(displayName !== undefined && { displayName }),
          ...(description !== undefined && { description }),
          ...(color !== undefined && { color }),
          ...(priority !== undefined && { priority }),
        },
      });

      // If permissionIds provided, replace all role-permission associations atomically
      if (Array.isArray(permissionIds)) {
        await tx.rolePermission.deleteMany({ where: { roleId: id } });
        if (permissionIds.length > 0) {
          await tx.rolePermission.createMany({
            data: permissionIds.map((permId: string) => ({
              roleId: id,
              permissionId: permId,
            })),
          });
        }
      }

      return updated;
    });

    // Fetch updated role with permissions (outside transaction for read)
    const roleWithPerms = await db.role.findUnique({
      where: { id },
      include: {
        permissions: { include: { permission: true } },
      },
    });

    await recordAudit({
      actorId: user.userId,
      actorType: "user",
      action: "role.update",
      resource: "role",
      resourceId: id,
      resourceName: updatedRole.name,
      severity: "info",
      details: {
        updatedFields: Object.keys(body),
        permissionCount: permissionIds?.length ?? roleWithPerms?.permissions.length,
      },
    });

    return NextResponse.json({
      success: true,
      data: {
        ...roleWithPerms,
        permissions: roleWithPerms?.permissions.map((rp) => rp.permission) ?? [],
      },
    });
  } catch (error) {
    console.error("[RBAC Role PUT]", error);
    return NextResponse.json(
      { success: false, error: "Error al actualizar rol", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "role", "delete");
  if (authResult instanceof NextResponse) return authResult;
  const { user } = authResult;

  try {
    const { id } = await params;

    const role = await db.role.findUnique({
      where: { id },
      include: {
        _count: { select: { users: true } },
      },
    });
    if (!role) {
      return NextResponse.json(
        { success: false, error: "Rol no encontrado", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    if (role.isSystem) {
      return NextResponse.json(
        { success: false, error: "Los roles de sistema no pueden ser eliminados", code: "FORBIDDEN" },
        { status: 403 },
      );
    }

    // Warn if role has active user assignments
    if (role._count.users > 0) {
      return NextResponse.json(
        {
          success: false,
          error: `El rol tiene ${role._count.users} usuario(s) asignado(s). Revoque las asignaciones primero.`,
          code: "CONFLICT",
          affectedUsers: role._count.users,
        },
        { status: 409 },
      );
    }

    // Delete role (cascades will handle RolePermission — UserRole already empty)
    await db.role.delete({ where: { id } });

    await recordAudit({
      actorId: user.userId,
      actorType: "user",
      action: "role.delete",
      resource: "role",
      resourceId: id,
      resourceName: role.name,
      severity: "warn",
      details: { deletedRole: role.name, displayName: role.displayName },
    });

    return NextResponse.json({
      success: true,
      data: { id, name: role.name },
      message: "Rol eliminado exitosamente",
    });
  } catch (error) {
    console.error("[RBAC Role DELETE]", error);
    return NextResponse.json(
      { success: false, error: "Error al eliminar rol", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
