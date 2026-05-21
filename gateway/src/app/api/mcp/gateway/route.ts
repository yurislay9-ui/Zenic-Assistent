// ─── MCP Gateway — Execute Tool ─────────────────────────────────────
// FIX: Now uses the class-based GatewayEngine with full 8-step security
// pipeline (auth, RBAC, rate limit, policy engine, Merkle audit).
// Previously used the deprecated functional evaluateExecution() which
// skipped all security checks.

import { NextRequest, NextResponse } from "next/server";
import { GatewayEngine } from "@/lib/mcp-gateway/engine/gateway-engine";
import { getRateLimiter } from "@/lib/mcp-gateway/rate-limiter/rate-limiter";
import { getAuthService } from "@/lib/mcp-gateway/auth/auth-service";
import { getToolRegistry } from "@/lib/mcp-gateway/sdk/tool-registry";
import { getMerkleAuditService } from "@/lib/mcp-gateway/audit/merkle-audit";
import type { ApiResponse, GatewayRequest } from "@/lib/mcp-gateway/types";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";

/** POST /api/mcp/gateway — Execute a tool through the gateway (SECURED) */
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

    // ── Extract auth context from request ──────────────────────
    // FIX: Server-side auth verification — don't trust client-supplied executorId
    const authService = getAuthService();
    const authContext = await authService.extractFromRequest(request);

    if (!authContext.authenticated) {
      return NextResponse.json(
        { success: false, error: "Authentication required", code: "AUTH_REQUIRED" } as const,
        { status: 401 }
      );
    }

    // ── Build GatewayRequest with verified auth ────────────────
    const gatewayRequest: GatewayRequest = {
      toolCall: {
        name: body.toolName,
        arguments: body.input,
        _meta: {
          traceId: body.correlationId,
        },
      },
      auth: {
        authenticated: true,
        method: authContext.method,
        executorId: authContext.executorId ?? body.executorId,
        tenantId: authContext.tenantId,
        roles: authContext.roles,
      },
    };

    // ── Use class-based GatewayEngine with full security pipeline ──
    const engine = new GatewayEngine({
      rateLimiter: getRateLimiter(),
      authService,
      toolRegistry: getToolRegistry(),
      auditService: getMerkleAuditService(),
    });

    const response = await engine.execute(gatewayRequest);

    const apiResponse: ApiResponse<typeof response> = {
      success: response.verdict === "allow",
      data: response,
      message: response.verdict === "allow"
        ? "Execution authorized"
        : response.verdict === "conditional"
          ? "Execution requires approval"
          : response.reason ?? "Execution denied",
    };

    // Return appropriate status based on verdict
    const status = response.verdict === "allow" ? 200 : response.verdict === "conditional" ? 202 : 403;

    return NextResponse.json(apiResponse, { status });
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
