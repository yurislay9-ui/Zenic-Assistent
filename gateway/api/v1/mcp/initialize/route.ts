// ─── Zenic-Agents v3 — MCP Gateway Initialization ─────────────────
// POST /api/v1/mcp/initialize — MCP protocol handshake

import { NextRequest, NextResponse } from "next/server";
import { parseJsonRpcRequest, successResponse, errorResponse } from "@/lib/mcp-gateway/protocol";
import { MCP_PROTOCOL_VERSION, ZENIC_GATEWAY_VERSION, JSON_RPC_ERRORS } from "@/lib/mcp-gateway/protocol/types";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = parseJsonRpcRequest(body);

    if (!parsed.ok) {
      return NextResponse.json(errorResponse(null, parsed.error), { status: 400 });
    }

    const { id, params } = parsed.request;

    // Respond with server capabilities
    return NextResponse.json(
      successResponse(id, {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {
          tools: { listChanged: true },
          resources: { subscribe: true, listChanged: true },
          prompts: { listChanged: true },
        },
        serverInfo: {
          name: "Zenic MCP Gateway",
          version: ZENIC_GATEWAY_VERSION,
        },
        _meta: {
          gatewayFeatures: ["rbac", "rate_limiting", "merkle_audit", "policy_engine", "approval_chain"],
          supportedAuthMethods: ["api_key", "bearer_token"],
          protocolVersion: MCP_PROTOCOL_VERSION,
        },
      })
    );
  } catch {
    return NextResponse.json(
      errorResponse(null, JSON_RPC_ERRORS.PARSE_ERROR),
      { status: 400 }
    );
  }
}
