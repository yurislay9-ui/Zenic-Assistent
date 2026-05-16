// ─── Zenic-Agents v3 — HITL API: Approval Statistics ─────────────────
// GET /api/v1/hitl/stats — Get approval statistics

import { NextResponse } from "next/server";
import { getApprovalEngine } from "@/lib/hitl";

// GET /api/v1/hitl/stats
export async function GET() {
  try {
    const engine = getApprovalEngine();
    const stats = await engine.getStats();

    return NextResponse.json({
      success: true,
      data: stats,
    });
  } catch (error) {
    console.error("[HITL GET stats]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch approval statistics", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
