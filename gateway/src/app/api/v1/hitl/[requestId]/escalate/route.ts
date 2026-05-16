// ─── Zenic-Agents v3 — HITL API: Escalate Request ────────────────────
// POST /api/v1/hitl/[requestId]/escalate

import { NextRequest, NextResponse } from "next/server";
import { getEscalationService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// POST /api/v1/hitl/[requestId]/escalate
export async function POST(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;
    const body = await request.json();

    if (!body.toRole) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required field: toRole",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const service = getEscalationService();
    const result = await service.escalateRequest(requestId, {
      fromUserId: body.fromUserId,
      toUserId: body.toUserId,
      toRole: body.toRole,
      reason: body.reason,
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
      if (error.message.includes("Cannot escalate") || error.message.includes("Maximum escalation")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "CONFLICT" },
          { status: 409 },
        );
      }
    }
    console.error("[HITL POST escalate]", error);
    return NextResponse.json(
      { success: false, error: "Failed to escalate request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
