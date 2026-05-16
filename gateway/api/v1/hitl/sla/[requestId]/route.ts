// ─── Zenic-Agents v3 — HITL API: Get SLA Record for Request ───────────
// GET /api/v1/hitl/sla/[requestId]

import { NextRequest, NextResponse } from "next/server";
import { getSLAService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// GET /api/v1/hitl/sla/[requestId]
export async function GET(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;

    const service = getSLAService();
    const result = await service.getSLARecord(requestId);

    if (!result) {
      return NextResponse.json({
        success: true,
        data: null,
      });
    }

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[HITL GET sla/requestId]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch SLA record", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
