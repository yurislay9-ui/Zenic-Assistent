import { NextRequest, NextResponse } from "next/server";
import { checkPermission } from "@/lib/mcp-gateway/services/rbac-service";
import type { PermissionCheck, PermissionCheckResult } from "@/lib/mcp-gateway/types";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { userId, resource, action, context } = body as PermissionCheck;

    if (!userId || !resource || !action) {
      return NextResponse.json(
        { success: false, error: "userId, resource, and action are required", code: "VALIDATION_ERROR" },
        { status: 400 }
      );
    }

    const result: PermissionCheckResult = await checkPermission({
      userId,
      resource,
      action,
      context,
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[RBAC Check POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to check permission", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}
