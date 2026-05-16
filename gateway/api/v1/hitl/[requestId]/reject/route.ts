// ─── Zenic-Agents v3 — HITL API: Reject Request ──────────────────────
// POST /api/v1/hitl/[requestId]/reject

import { NextRequest, NextResponse } from "next/server";
import { getApprovalEngine } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// POST /api/v1/hitl/[requestId]/reject
export async function POST(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;
    const body = await request.json();

    if (!body.decisionBy || !body.decisionByName || !body.role || !body.comment) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: decisionBy, decisionByName, role, comment (rejection reason is required)",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const engine = getApprovalEngine();
    const result = await engine.rejectRequest(requestId, {
      decisionBy: body.decisionBy,
      decisionByName: body.decisionByName,
      role: body.role,
      comment: body.comment,
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    if (error instanceof Error) {
      if (error.message.includes("not found")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "NOT_FOUND" },
          { status: 404 },
        );
      }
      if (error.message.includes("Cannot reject")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "CONFLICT" },
          { status: 409 },
        );
      }
    }
    console.error("[HITL POST reject]", error);
    return NextResponse.json(
      { success: false, error: "Failed to reject request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
