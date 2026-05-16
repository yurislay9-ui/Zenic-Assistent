// ─── Zenic-Agents v3 — MCP Tool Call (Gateway Core) ──────────────
// POST /api/v1/mcp/call — Execute a tool through the full gateway pipeline
// Phase 2: Now uses ObservableGatewayEngine for distributed tracing + metrics

import { NextRequest, NextResponse } from "next/server";
import { parseJsonRpcRequest, successResponse, errorResponse, isErrorResponse } from "@/lib/mcp-gateway/protocol";
import { JSON_RPC_ERRORS, MCP_METHODS } from "@/lib/mcp-gateway/protocol/types";
import type { McpToolCallParams } from "@/lib/mcp-gateway/protocol/types";
import { getRegistry } from "@/lib/mcp-gateway/sdk/sdk";
import { initializeGateway, getObservableGateway } from "@/lib/mcp-gateway/bootstrap";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = parseJsonRpcRequest(body);

    if (!parsed.ok) {
      return NextResponse.json(errorResponse(null, parsed.error), { status: 400 });
    }

    const { id, method, params } = parsed.request;

    // Handle different MCP methods
    if (method === MCP_METHODS.INITIALIZE) {
      return NextResponse.json(
        successResponse(id, {
          protocolVersion: "2024-11-05",
          capabilities: { tools: { listChanged: true } },
          serverInfo: { name: "Zenic MCP Gateway", version: "3.0.0" },
        })
      );
    }

    if (method === MCP_METHODS.TOOLS_LIST) {
      const registry = getRegistry();
      return NextResponse.json(
        successResponse(id, { tools: registry.listMcpDefinitions() })
      );
    }

    if (method === MCP_METHODS.TOOLS_CALL) {
      return await handleToolCall(id, params as McpToolCallParams, request);
    }

    // Unknown method
    return NextResponse.json(
      errorResponse(id, JSON_RPC_ERRORS.METHOD_NOT_FOUND),
      { status: 400 }
    );
  } catch (error) {
    console.error("[MCP Call Error]", error);
    return NextResponse.json(
      errorResponse(null, {
        code: -32603,
        message: "Internal error",
        data: error instanceof Error ? error.message : String(error),
      }),
      { status: 500 }
    );
  }
}

async function handleToolCall(
  id: string | number | null,
  params: McpToolCallParams,
  request: NextRequest
) {
  // Get the observable gateway (wraps engine with tracing + metrics)
  const observableEngine = getObservableGateway();
  const innerEngine = observableEngine.getInner();

  // Authenticate from headers
  const headers: Record<string, string | undefined> = {};
  request.headers.forEach((value, key) => {
    headers[key] = value;
  });

  const authResult = innerEngine["authService"].authenticate(headers as Record<string, string>);

  // Execute through the observable gateway pipeline (traces every step)
  const response = await observableEngine.execute({
    requestId: id,
    toolCall: params,
    auth: authResult,
    ipAddress: headers["x-forwarded-for"] ?? headers["x-real-ip"],
    userAgent: headers["user-agent"],
  });

  // Map verdict to JSON-RPC response
  if (response.verdict === "deny") {
    const errorCode =
      !authResult.authenticated ? -32005 :  // AUTH_REQUIRED
      response.pipeline.some((s) => s.name === "rate_limit" && !s.passed) ? -32004 : // RATE_LIMIT
      response.pipeline.some((s) => s.name === "rbac_check" && !s.passed) ? -32003 : // PERMISSION_DENIED
      -32001; // TOOL_NOT_FOUND or generic deny

    return NextResponse.json(
      errorResponse(id, {
        code: errorCode,
        message: response.reason,
        data: {
          executionId: response.executionId,
          verdict: response.verdict,
          pipeline: response.pipeline,
          duration: response.duration,
        },
      }),
      { status: errorCode === -32004 ? 429 : 403 }
    );
  }

  if (response.verdict === "conditional") {
    return NextResponse.json(
      successResponse(id, {
        content: [{ type: "text", text: response.reason }],
        _meta: {
          executionId: response.executionId,
          verdict: "conditional",
          requiresApproval: true,
          pipeline: response.pipeline,
          duration: response.duration,
        },
      }),
      { status: 202 }
    );
  }

  // verdict === "allow"
  return NextResponse.json(
    successResponse(id, response.result ?? {
      content: [{ type: "text", text: "Execution completed" }],
      _meta: { executionId: response.executionId, verdict: "allow", duration: response.duration },
    })
  );
}
