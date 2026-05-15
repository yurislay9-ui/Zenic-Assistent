// ─── Zenic-Agents v3 — Policy Engine API: Namespace Hierarchy ─────────
// GET /api/v1/policy-engine/namespaces/[namespaceId]/hierarchy — Get namespace hierarchy

import { NextRequest, NextResponse } from "next/server";
import { getNamespaceHierarchy } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/namespaces/[namespaceId]/hierarchy
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ namespaceId: string }> },
) {
  try {
    const { namespaceId } = await params;

    const hierarchy = await getNamespaceHierarchy(namespaceId);

    if (hierarchy.length === 0) {
      return NextResponse.json(
        { success: false, error: `Namespace "${namespaceId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: hierarchy,
    });
  } catch (error) {
    console.error("[PolicyEngine Namespace Hierarchy GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to get namespace hierarchy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
