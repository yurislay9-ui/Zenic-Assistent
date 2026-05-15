// ─── Zenic-Agents v3 — MCP Tool Registration ─────────────────────
// POST /api/v1/mcp/tools/register — Register new MCP tools via SDK

import { NextRequest, NextResponse } from "next/server";
import { parseJsonRpcRequest, successResponse, errorResponse } from "@/lib/mcp-gateway/protocol";
import { JSON_RPC_ERRORS, MCP_METHODS } from "@/lib/mcp-gateway/protocol/types";
import { getRegistry } from "@/lib/mcp-gateway/sdk/sdk";
import type { SdkToolConfig } from "@/lib/mcp-gateway/sdk/types";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const parsed = parseJsonRpcRequest(body);

    if (!parsed.ok) {
      return NextResponse.json(errorResponse(null, parsed.error), { status: 400 });
    }

    const { id, method, params } = parsed.request;

    if (method !== MCP_METHODS.TOOLS_REGISTER) {
      return NextResponse.json(
        errorResponse(id, JSON_RPC_ERRORS.METHOD_NOT_FOUND),
        { status: 400 }
      );
    }

    const registry = getRegistry();
    const toolDefs = (params?.tools ?? []) as Array<Partial<SdkToolConfig> & { name: string; description: string; inputSchema: SdkToolConfig["inputSchema"] }>;

    const results: Array<{ name: string; status: "registered" | "error"; error?: string }> = [];

    for (const toolDef of toolDefs) {
      try {
        // Register with a passthrough handler (external tools must provide their own)
        registry.register({
          name: toolDef.name,
          displayName: toolDef.displayName ?? toolDef.name.replace(/_/g, " "),
          description: toolDef.description,
          category: toolDef.category ?? "external",
          riskLevel: toolDef.riskLevel ?? "medium",
          inputSchema: toolDef.inputSchema,
          permissions: toolDef.permissions ?? [],
          rateLimit: toolDef.rateLimit,
          requiresApproval: toolDef.requiresApproval,
          handler: async (input, ctx) => ({
            success: false,
            error: "External tool handler not connected — use gateway call endpoint",
          }),
        }, "sdk");
        results.push({ name: toolDef.name, status: "registered" });
      } catch (err) {
        results.push({
          name: toolDef.name,
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }

    return NextResponse.json(
      successResponse(id, { registered: results })
    );
  } catch {
    return NextResponse.json(
      errorResponse(null, JSON_RPC_ERRORS.INTERNAL_ERROR),
      { status: 500 }
    );
  }
}
