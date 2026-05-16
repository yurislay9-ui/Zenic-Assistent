// ─── Zenic-Agents v3 — HITL API: Undo Approved Action ────────────────
// POST /api/v1/hitl/[requestId]/undo

import { NextRequest, NextResponse } from "next/server";
import { getReversibleActionService } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// POST /api/v1/hitl/[requestId]/undo
export async function POST(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;
    const body = await request.json();

    if (!body.undoBy || !body.undoByName || !body.reason) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: undoBy, undoByName, reason",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const service = getReversibleActionService();

    // First check if undo is available
    const undoStatus = await service.isUndoAvailable(requestId);
    if (!undoStatus.canUndo) {
      return NextResponse.json(
        {
          success: false,
          error: `Undo not available: ${undoStatus.reason}`,
          code: "CONFLICT",
          undoStatus,
        },
        { status: 409 },
      );
    }

    const result = await service.undoAction(requestId, {
      undoBy: body.undoBy,
      undoByName: body.undoByName,
      reason: body.reason,
      undoType: body.undoType,
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
      if (error.message.includes("not reversible") || error.message.includes("not been executed") || error.message.includes("already been undone") || error.message.includes("expired")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "CONFLICT" },
          { status: 409 },
        );
      }
    }
    console.error("[HITL POST undo]", error);
    return NextResponse.json(
      { success: false, error: "Failed to undo action", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
