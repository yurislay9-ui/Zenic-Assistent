import { NextRequest, NextResponse } from "next/server";
import { revokeRole } from "@/lib/mcp-gateway/services/rbac-service";
import { db } from "@/lib/db";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { userId, roleId, revokedBy } = body as {
      userId: string;
      roleId: string;
      revokedBy: string;
    };

    if (!userId || !roleId || !revokedBy) {
      return NextResponse.json(
        { success: false, error: "userId, roleId, and revokedBy are required", code: "VALIDATION_ERROR" },
        { status: 400 }
      );
    }

    // Check if assignment exists
    const existing = await db.userRole.findUnique({
      where: { userId_roleId: { userId, roleId } },
    });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Role assignment not found", code: "NOT_FOUND" },
        { status: 404 }
      );
    }

    await revokeRole(userId, roleId, revokedBy);

    return NextResponse.json({
      success: true,
      data: { userId, roleId },
      message: "Role revoked successfully",
    });
  } catch (error) {
    console.error("[RBAC Revoke POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to revoke role", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
