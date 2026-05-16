// ─── Zenic-Agents v3 — HITL API: Get Evidence for Request ─────────────
// GET /api/v1/hitl/evidence/[requestId]

import { NextRequest, NextResponse } from "next/server";
import { getEvidenceService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// GET /api/v1/hitl/evidence/[requestId]
export async function GET(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;

    const service = getEvidenceService();
    const result = await service.getEvidence(requestId);

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    if (error instanceof Error && error.message.includes("not found")) {
      return NextResponse.json(
        { success: false, error: error.message, code: "NOT_FOUND" },
        { status: 404 },
      );
    }
    console.error("[HITL GET evidence/requestId]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch evidence", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
