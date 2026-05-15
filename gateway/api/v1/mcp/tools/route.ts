// ─── Zenic-Agents v3 — MCP Tools List ─────────────────────────────
// GET|POST /api/v1/mcp/tools — List available MCP tools

import { NextRequest, NextResponse } from "next/server";
import { parseJsonRpcRequest, successResponse, errorResponse } from "@/lib/mcp-gateway/protocol";
import { JSON_RPC_ERRORS, MCP_METHODS } from "@/lib/mcp-gateway/protocol/types";
import { getRegistry } from "@/lib/mcp-gateway/sdk/sdk";
import { initializeGateway } from "@/lib/mcp-gateway/bootstrap";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = parseJsonRpcRequest(body);

    if (!parsed.ok) {
      return NextResponse.json(errorResponse(null, parsed.error), { status: 400 });
    }

    const { id, method } = parsed.request;

    if (method !== MCP_METHODS.TOOLS_LIST) {
      return NextResponse.json(
        errorResponse(id, JSON_RPC_ERRORS.METHOD_NOT_FOUND),
        { status: 400 }
      );
    }

    const registry = getRegistry();
    const tools = registry.listMcpDefinitions();

    return NextResponse.json(
      successResponse(id, { tools })
    );
  } catch {
    return NextResponse.json(
      errorResponse(null, JSON_RPC_ERRORS.INTERNAL_ERROR),
      { status: 500 }
    );
  }
}

export async function GET() {
  // Initialize gateway to register native executors
  initializeGateway();
  const registry = getRegistry();
  const tools = registry.listMcpDefinitions();
  const entries = registry.list();

  return NextResponse.json({
    success: true,
    data: {
      tools,
      total: entries.length,
      byCategory: Object.groupBy(entries, (e) => e.config.category),
      byRiskLevel: Object.groupBy(entries, (e) => e.config.riskLevel),
      bySource: Object.groupBy(entries, (e) => e.source),
    },
  });
}
