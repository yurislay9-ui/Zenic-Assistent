// ─── MCP Gateway — Approve Pending Execution ───────────────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { approveExecution } from "@/lib/mcp-gateway/services/gateway-engine";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";

interface ApproveRequestBody {
  executionId: string;
  approverId: string;
}

/** POST /api/mcp/gateway/approve — Approve a pending execution */
export async function POST(request: NextRequest) {
  try {
    const body: ApproveRequestBody = await request.json();

    // Validate required fields
    if (!body.executionId || typeof body.executionId !== "string") {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: executionId", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    if (!body.approverId || typeof body.approverId !== "string") {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: approverId", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    // Check that the execution exists and is in pending state
    const execution = await db.toolExecution.findUnique({
      where: { id: body.executionId },
    });

    if (!execution) {
      return NextResponse.json(
        { success: false, error: "Execution not found", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    if (execution.status !== "pending") {
      return NextResponse.json(
        { success: false, error: `Cannot approve execution in "${execution.status}" status. Only pending executions can be approved.`, code: "INVALID_STATE" } as const,
        { status: 400 }
      );
    }

    // Approve the execution
    const approved = await approveExecution(body.executionId, body.approverId);

    const response = {
      success: true,
      data: {
        id: approved.id,
        status: approved.status,
        verdict: approved.verdict,
        verdictReason: approved.verdictReason,
        toolId: approved.toolId,
        executorId: approved.executorId,
        updatedAt: approved.completedAt,
      },
      message: "Execution approved successfully",
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[POST /api/mcp/gateway/approve]", error);

    // The Prisma update may throw if the record is not found or not in pending state
    if (error instanceof Error && error.message.includes("Record to update not found")) {
      return NextResponse.json(
        { success: false, error: "Execution not found or not in pending state", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    // Record audit error
    await recordAudit({
      action: "execution.approve",
      resource: "execution",
      severity: "error",
      outcome: "error",
      details: { error: error instanceof Error ? error.message : "Unknown error" },
    }).catch(() => {});

    return NextResponse.json(
      { success: false, error: "Failed to approve execution", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}
