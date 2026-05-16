// ─── Zenic-Agents v3 — HITL API: Pending Approvals ──────────────────
// GET /api/v1/hitl/pending — List pending approvals for current user

import { NextRequest, NextResponse } from "next/server";
import { getApprovalEngine } from "@/lib/hitl";

// GET /api/v1/hitl/pending
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const userId = searchParams.get("userId");

    if (!userId) {
      return NextResponse.json(
        { success: false, error: "Missing required query parameter: userId", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const engine = getApprovalEngine();
    const data = await engine.listPendingForUser(userId);

    return NextResponse.json({
      success: true,
      data,
      total: data.length,
    });
  } catch (error) {
    console.error("[HITL GET pending]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch pending approvals", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
