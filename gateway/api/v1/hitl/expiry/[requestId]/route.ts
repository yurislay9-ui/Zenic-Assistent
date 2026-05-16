// ─── Zenic-Agents v3 — HITL API: Get Expiry Record for Request ────────
// GET /api/v1/hitl/expiry/[requestId]

import { NextRequest, NextResponse } from "next/server";
import { getExpiryService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// GET /api/v1/hitl/expiry/[requestId]
export async function GET(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;

    const service = getExpiryService();
    const result = await service.getExpiryRecord(requestId);

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
    console.error("[HITL GET expiry/requestId]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch expiry record", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
