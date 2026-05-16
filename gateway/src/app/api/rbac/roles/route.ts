import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { createRole } from "@/lib/mcp-gateway/services/rbac-service";
import type { PaginatedResponse, RoleDTO } from "@/lib/mcp-gateway/types";

export async function GET(request: NextRequest) {
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
          users: {
            select: { id: true },
          },
        },
        orderBy: { priority: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.role.count(),
    ]);

    const data = roles.map(({ users: _users, ...role }) => ({
      ...role,
      permissions: role.permissions.map((rp) => rp.permission),
      userCount: _users?.length ?? 0,
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
      { success: false, error: "Failed to fetch roles", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name, displayName, description, color, isSystem, priority, permissionIds } = body as RoleDTO;

    if (!name || !displayName) {
      return NextResponse.json(
        { success: false, error: "name and displayName are required", code: "VALIDATION_ERROR" },
        { status: 400 }
      );
    }

    // Check for duplicate name
    const existing = await db.role.findUnique({ where: { name } });
    if (existing) {
      return NextResponse.json(
        { success: false, error: `Role "${name}" already exists`, code: "DUPLICATE" },
        { status: 409 }
      );
    }

    const role = await createRole(
      {
        name,
        displayName,
        description: description ?? "",
        color: color ?? "#6b7280",
        isSystem: isSystem ?? false,
        priority: priority ?? 0,
        permissionIds: permissionIds ?? [],
      },
      "api"
    );

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
      { status: 201 }
    );
  } catch (error) {
    console.error("[RBAC Roles POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create role", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
