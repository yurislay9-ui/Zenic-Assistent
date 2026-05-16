// ─── Zenic-Agents v3 — HITL API: Delegate Request ────────────────────
// POST /api/v1/hitl/[requestId]/delegate

import { NextRequest, NextResponse } from "next/server";
import { getDelegationService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// POST /api/v1/hitl/[requestId]/delegate
export async function POST(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;
    const body = await request.json();

    if (!body.fromUserId || !body.fromUserName || !body.toUserId || !body.toUserName) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: fromUserId, fromUserName, toUserId, toUserName",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const service = getDelegationService();
    const result = await service.delegateRequest(requestId, {
      fromUserId: body.fromUserId,
      fromUserName: body.fromUserName,
      toUserId: body.toUserId,
      toUserName: body.toUserName,
      reason: body.reason,
      expiresAt: body.expiresAt,
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
      if (error.message.includes("Cannot delegate") || error.message.includes("yourself") || error.message.includes("depth") || error.message.includes("already has")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "CONFLICT" },
          { status: 409 },
        );
      }
    }
    console.error("[HITL POST delegate]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delegate request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
