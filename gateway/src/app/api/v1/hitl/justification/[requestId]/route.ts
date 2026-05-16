// ─── Zenic-Agents v3 — HITL API: Get Justification for Request ────────
// GET /api/v1/hitl/justification/[requestId]

import { NextRequest, NextResponse } from "next/server";
import { getJustificationService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// GET /api/v1/hitl/justification/[requestId]
export async function GET(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;

    const service = getJustificationService();
    const result = await service.getJustification(requestId);

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
    console.error("[HITL GET justification/requestId]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch justification", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
