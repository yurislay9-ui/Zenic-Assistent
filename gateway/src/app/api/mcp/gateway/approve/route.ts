// ─── MCP Gateway — Approve Pending Execution ───────────────────────
// FIX: Now verifies the caller's RBAC role server-side before allowing
// approval. Previously accepted approverId from request body without
// verification, allowing any authenticated user to approve executions.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { approveExecution } from "@/lib/mcp-gateway/services/gateway-engine";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import { getAuthService } from "@/lib/mcp-gateway/auth/auth-service";

// FIX: RBAC-verified approval — only admin/operator roles can approve
const APPROVER_ROLES = ["admin", "operator"];

interface ApproveRequestBody {
  executionId: string;
  approverId?: string; // DEPRECATED — now extracted from auth context
}

/** POST /api/mcp/gateway/approve — Approve a pending execution (RBAC-SECURED) */
export async function POST(request: NextRequest) {
  try {
    // ── Step 1: Verify caller authentication ────────────────────
    const authService = getAuthService();
    const authContext = await authService.extractFromRequest(request);

    if (!authContext.authenticated) {
      return NextResponse.json(
        { success: false, error: "Authentication required", code: "AUTH_REQUIRED" } as const,
        { status: 401 }
      );
    }

    // ── Step 2: Verify caller has approval authority (RBAC) ─────
    const callerRoles = authContext.roles ?? [];
    const hasApprovalAuthority = callerRoles.some((role: string) => APPROVER_ROLES.includes(role));

    if (!hasApprovalAuthority) {
      // Audit the unauthorized approval attempt
      await recordAudit({
        action: "execution.approve.unauthorized",
        resource: "execution",
        severity: "warn",
        outcome: "denied",
        details: {
          callerId: authContext.executorId,
          callerRoles,
          requiredRoles: APPROVER_ROLES,
        },
      }).catch(() => {});

      return NextResponse.json(
        {
          success: false,
          error: "Insufficient permissions — approval requires admin or operator role",
          code: "FORBIDDEN",
        } as const,
        { status: 403 }
      );
    }

    // ── Step 3: Use server-verified identity as approver ────────
    const body: ApproveRequestBody = await request.json();

    if (!body.executionId || typeof body.executionId !== "string") {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: executionId", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    // FIX: Use server-verified identity, NOT client-supplied approverId
    const verifiedApproverId = authContext.executorId ?? "unknown";

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

    // Approve with verified identity
    const approved = await approveExecution(body.executionId, verifiedApproverId);

    // Audit successful approval
    await recordAudit({
      action: "execution.approve",
      resource: "execution",
      severity: "info",
      outcome: "success",
      details: {
        executionId: body.executionId,
        approverId: verifiedApproverId,
        approverRoles: callerRoles,
      },
    }).catch(() => {});

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
