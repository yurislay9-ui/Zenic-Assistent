// ─── MCP Gateway — Execute Tool ─────────────────────────────────────

import { NextRequest, NextResponse } from "next/server";
import { evaluateExecution } from "@/lib/mcp-gateway/services/gateway-engine";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { ApiResponse, ExecutionRequest, VerdictResponse } from "@/lib/mcp-gateway/types";

/** POST /api/mcp/gateway — Execute a tool through the gateway */
export async function POST(request: NextRequest) {
  try {
    const body: {
      toolName: string;
      input: Record<string, unknown>;
      executorId?: string;
      correlationId?: string;
    } = await request.json();

    // Validate required fields
    if (!body.toolName || typeof body.toolName !== "string") {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: toolName", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    if (!body.input || typeof body.input !== "object" || Array.isArray(body.input)) {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: input (must be an object)", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    // Build execution request
    const executionRequest: ExecutionRequest = {
      toolName: body.toolName,
      input: body.input,
      executorId: body.executorId,
      correlationId: body.correlationId,
    };

    // Evaluate execution through gateway engine
    const verdict: VerdictResponse = await evaluateExecution(executionRequest);

    const response: ApiResponse<VerdictResponse> = {
      success: true,
      data: verdict,
      message: verdict.verdict === "allow"
        ? "Execution authorized"
        : verdict.verdict === "conditional"
          ? "Execution requires approval"
          : "Execution denied",
    };

    // Return appropriate status based on verdict
    const status = verdict.verdict === "allow" ? 200 : verdict.verdict === "conditional" ? 202 : 403;

    return NextResponse.json(response, { status });
  } catch (error) {
    console.error("[POST /api/mcp/gateway]", error);

    // Record the error in audit
    await recordAudit({
      action: "gateway.execute",
      resource: "execution",
      severity: "error",
      outcome: "error",
      details: {
        error: error instanceof Error ? error.message : "Unknown error",
      },
    }).catch(() => {
      // Don't fail the response if audit logging fails
    });

    return NextResponse.json(
      { success: false, error: "Gateway execution failed", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}
