import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import type { PaginatedResponse } from "@/lib/mcp-gateway/types";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const resource = searchParams.get("resource") || undefined;
    const action = searchParams.get("action") || undefined;
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 50));

    const where: Record<string, unknown> = {};
    if (resource) where.resource = resource;
    if (action) where.action = action;

    const [permissions, total] = await Promise.all([
      db.permission.findMany({
        where,
        orderBy: [{ resource: "asc" }, { action: "asc" }],
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.permission.count({ where }),
    ]);

    // If no specific filter, return all without pagination (small dataset)
    if (!resource && !action) {
      const allPermissions = await db.permission.findMany({
        orderBy: [{ resource: "asc" }, { action: "asc" }],
      });
      return NextResponse.json({
        success: true,
        data: allPermissions,
        total: allPermissions.length,
        page: 1,
        pageSize: allPermissions.length,
        totalPages: 1,
      } satisfies PaginatedResponse<typeof allPermissions[number]>);
    }

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
      { success: false, error: "Failed to fetch permissions", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
