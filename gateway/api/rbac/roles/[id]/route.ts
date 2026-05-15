import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
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
        { success: false, error: "Role not found", code: "NOT_FOUND" },
        { status: 404 }
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
      { success: false, error: "Failed to fetch role", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const existing = await db.role.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Role not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    const body = await request.json();
    const { name, displayName, description, color, priority, permissionIds } = body;

    // Update role fields
    const updatedRole = await db.role.update({
      where: { id },
      data: {
        ...(name !== undefined && { name }),
        ...(displayName !== undefined && { displayName }),
        ...(description !== undefined && { description }),
        ...(color !== undefined && { color }),
        ...(priority !== undefined && { priority }),
      },
    });

    // If permissionIds provided, replace all role-permission associations
    if (Array.isArray(permissionIds)) {
      await db.rolePermission.deleteMany({ where: { roleId: id } });
      if (permissionIds.length > 0) {
        await db.rolePermission.createMany({
          data: permissionIds.map((permId: string) => ({
            roleId: id,
            permissionId: permId,
          })),
        });
      }
    }

    // Fetch updated role with permissions
    const roleWithPerms = await db.role.findUnique({
      where: { id },
      include: {
        permissions: { include: { permission: true } },
      },
    });

    await recordAudit({
      actorId: "api",
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
      { success: false, error: "Failed to update role", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const role = await db.role.findUnique({ where: { id } });
    if (!role) {
      return NextResponse.json(
        { success: false, error: "Role not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    if (role.isSystem) {
      return NextResponse.json(
        { success: false, error: "System roles cannot be deleted", code: "FORBIDDEN" },
        { status: 403 }
      );
    }

    // Delete role (cascades will handle RolePermission and UserRole)
    await db.role.delete({ where: { id } });

    await recordAudit({
      actorId: "api",
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
      message: "Role deleted successfully",
    });
  } catch (error) {
    console.error("[RBAC Role DELETE]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete role", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
