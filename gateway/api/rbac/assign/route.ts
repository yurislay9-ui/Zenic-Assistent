import { NextRequest, NextResponse } from "next/server";
import { assignRole } from "@/lib/mcp-gateway/services/rbac-service";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { userId, roleId, grantedBy, expiresAt } = body as {
      userId: string;
      roleId: string;
      grantedBy: string;
      expiresAt?: string;
    };

    if (!userId || !roleId || !grantedBy) {
      return NextResponse.json(
        { success: false, error: "userId, roleId, and grantedBy are required", code: "VALIDATION_ERROR" },
        { status: 400 }
      );
    }

    // Verify role exists
    const { db } = await import("@/lib/db");
    const role = await db.role.findUnique({ where: { id: roleId } });
    if (!role) {
      return NextResponse.json(
        { success: false, error: "Role not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    // Verify user exists
    const user = await db.user.findUnique({ where: { id: userId } });
    if (!user) {
      return NextResponse.json(
        { success: false, error: "User not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    // Check if already assigned
    const existing = await db.userRole.findUnique({
      where: { userId_roleId: { userId, roleId } },
    });
    if (existing) {
      return NextResponse.json(
        { success: false, error: "Role already assigned to this user", code: "DUPLICATE" },
        { status: 409 }
      );
    }

    const expiresAtDate = expiresAt ? new Date(expiresAt) : undefined;

    // Validate expiry date is in the future
    if (expiresAtDate && expiresAtDate <= new Date()) {
      return NextResponse.json(
        { success: false, error: "expiresAt must be a future date", code: "VALIDATION_ERROR" },
        { status: 400 }
      );
    }

    const assignment = await assignRole(userId, roleId, grantedBy, expiresAtDate);

    return NextResponse.json({
      success: true,
      data: assignment,
    }, { status: 201 });
  } catch (error) {
    console.error("[RBAC Assign POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to assign role", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
