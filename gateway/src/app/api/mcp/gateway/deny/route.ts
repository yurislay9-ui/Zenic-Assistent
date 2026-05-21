// ─── MCP Gateway — Deny Pending Execution ───────────────────────────
// FIX: Now verifies the caller's RBAC role server-side before allowing
// denial. Previously accepted denierId from request body without
// verification, allowing any authenticated user to deny executions.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { denyExecution } from "@/lib/mcp-gateway/services/gateway-engine";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import { getAuthService } from "@/lib/mcp-gateway/auth/auth-service";

// FIX: RBAC-verified denial — only admin/operator roles can deny
const DENIER_ROLES = ["admin", "operator"];

interface DenyRequestBody {
  executionId: string;
  denierId?: string; // DEPRECATED — now extracted from auth context
  reason: string;
}

/** POST /api/mcp/gateway/deny — Deny a pending execution (RBAC-SECURED) */
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

    // ── Step 2: Verify caller has denial authority (RBAC) ───────
    const callerRoles = authContext.roles ?? [];
    const hasDenialAuthority = callerRoles.some((role: string) => DENIER_ROLES.includes(role));

    if (!hasDenialAuthority) {
      // Audit the unauthorized denial attempt
      await recordAudit({
        action: "execution.deny.unauthorized",
        resource: "execution",
        severity: "warn",
        outcome: "denied",
        details: {
          callerId: authContext.executorId,
          callerRoles,
          requiredRoles: DENIER_ROLES,
        },
      }).catch(() => {});

      return NextResponse.json(
        {
          success: false,
          error: "Insufficient permissions — denial requires admin or operator role",
          code: "FORBIDDEN",
        } as const,
        { status: 403 }
      );
    }

    // ── Step 3: Parse and validate request body ────────────────
    const body: DenyRequestBody = await request.json();

    if (!body.executionId || typeof body.executionId !== "string") {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: executionId", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    if (!body.reason || typeof body.reason !== "string" || body.reason.trim().length === 0) {
      return NextResponse.json(
        { success: false, error: "Missing or invalid required field: reason", code: "VALIDATION_ERROR" } as const,
        { status: 400 }
      );
    }

    // FIX: Use server-verified identity, NOT client-supplied denierId
    const verifiedDenierId = authContext.executorId ?? "unknown";

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

    // Deny with verified identity
    const denied = await denyExecution(body.executionId, verifiedDenierId, body.reason);

    // Audit successful denial
    await recordAudit({
      action: "execution.deny",
      resource: "execution",
      severity: "info",
      outcome: "success",
      details: {
        executionId: body.executionId,
        denierId: verifiedDenierId,
        denierRoles: callerRoles,
        reason: body.reason,
      },
    }).catch(() => {});

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
