// ─── Zenic-Agents v3 — RBAC Roles CRUD (Refactorizado FASE 9) ────────
// CAMBIOS:
// - Autenticación obligatoria en GET y POST
// - POST requiere role:write, GET requiere role:read
// - createRole con $transaction (race condition eliminada)
// - Audit logging en creación
// - Error genérico al cliente

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { createRole } from "@/lib/mcp-gateway/services/rbac-service";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import { requireAuthAndPermission } from "@/lib/rbac-auth";
import type { PaginatedResponse, RoleDTO } from "@/lib/mcp-gateway/types";

export async function GET(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "role", "read");
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20));

    const [roles, total] = await Promise.all([
      db.role.findMany({
        include: {
          permissions: {
            include: { permission: true },
          },
          _count: {
            select: { users: true },
          },
        },
        orderBy: { priority: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.role.count(),
    ]);

    const data = roles.map(({ _count, ...role }) => ({
      ...role,
      permissions: role.permissions.map((rp) => rp.permission),
      userCount: _count.users,
    }));

    const response: PaginatedResponse<typeof data[number]> = {
      success: true,
      data,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[RBAC Roles GET]", error);
    return NextResponse.json(
      { success: false, error: "Error al obtener roles", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  // ─── Auth + Permission Check ──────────────────────────────────────
  const authResult = await requireAuthAndPermission(request, "role", "write");
  if (authResult instanceof NextResponse) return authResult;
  const { user } = authResult;

  try {
    const body = await request.json();
    const { name, displayName, description, color, isSystem, priority, permissionIds } = body as RoleDTO;

    if (!name || !displayName) {
      return NextResponse.json(
        { success: false, error: "name y displayName son requeridos", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Prevent creating system roles via API
    if (isSystem) {
      return NextResponse.json(
        { success: false, error: "No se pueden crear roles de sistema vía API", code: "FORBIDDEN" },
        { status: 403 },
      );
    }

    const role = await createRole(
      {
        name,
        displayName,
        description: description ?? "",
        color: color ?? "#6b7280",
        isSystem: false,
        priority: priority ?? 0,
        permissionIds: permissionIds ?? [],
      },
      user.userId,
    );

    // Audit logging
    await recordAudit({
      actorId: user.userId,
      actorType: "user",
      action: "role.create",
      resource: "role",
      resourceId: role.id,
      resourceName: name,
      severity: "info",
      details: {
        displayName,
        permissionCount: permissionIds?.length ?? 0,
      },
    });

    // Fetch with permissions for response
    const roleWithPerms = await db.role.findUnique({
      where: { id: role.id },
      include: {
        permissions: { include: { permission: true } },
      },
    });

    return NextResponse.json(
      {
        success: true,
        data: {
          ...roleWithPerms,
          permissions: roleWithPerms?.permissions.map((rp) => rp.permission) ?? [],
        },
      },
      { status: 201 },
    );
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("DUPLICATE:")) {
      return NextResponse.json(
        { success: false, error: `Rol "${(error as Error).message.split('"')[1]}" ya existe`, code: "DUPLICATE" },
        { status: 409 },
      );
    }
    console.error("[RBAC Roles POST]", error);
    return NextResponse.json(
      { success: false, error: "Error al crear rol", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
