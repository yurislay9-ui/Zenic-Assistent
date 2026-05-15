// ─── MCP Gateway — Deny Pending Execution ───────────────────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { denyExecution } from "@/lib/mcp-gateway/services/gateway-engine";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";

interface DenyRequestBody {
  executionId: string;
  denierId: string;
  reason: string;
}

/** POST /api/mcp/gateway/deny — Deny a pending execution */
export async function POST(request: NextRequest) {
  try {
    const body: DenyRequestBody = await request.json();

    // Validate required fields
    if (!body.executionId || typeof body.executionId !== "string") {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: executionId", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    if (!body.denierId || typeof body.denierId !== "string") {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: denierId", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    if (!body.reason || typeof body.reason !== "string" || body.reason.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: reason", code: "VALIDATION_ERROR" } as const,
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
        { success: false, error: `Cannot deny execution in "${execution.status}" status. Only pending executions can be denied.`, code: "INVALID_STATE" } as const,
        { status: 400 }
      );
    }

    // Deny the execution
    const denied = await denyExecution(body.executionId, body.denierId, body.reason);

    const response = {
      success: true,
      data: {
        id: denied.id,
        status: denied.status,
        verdict: denied.verdict,
        verdictReason: denied.verdictReason,
        toolId: denied.toolId,
        executorId: denied.executorId,
        completedAt: denied.completedAt,
      },
      message: "Execution denied successfully",
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[POST /api/mcp/gateway/deny]", error);

    // The Prisma update may throw if the record is not found or not in pending state
    if (error instanceof Error && error.message.includes("Record to update not found")) {
      return NextResponse.json(
        { success: false, error: "Execution not found or not in pending state", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    // Record audit error
    await recordAudit({
      action: "execution.deny",
      resource: "execution",
      severity: "error",
      outcome: "error",
      details: { error: error instanceof Error ? error.message : "Unknown error" },
    }).catch(() => {});

    return NextResponse.json(
      { success: false, error: "Failed to deny execution", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}
