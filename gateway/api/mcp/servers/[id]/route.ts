// ─── MCP Servers CRUD — Get / Update / Delete by ID ────────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { ApiResponse, ServerDTO } from "@/lib/mcp-gateway/types";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/** Deserialize JSON fields on a server record */
function deserializeServer(server: Record<string, unknown>) {
  return {
    ...server,
    authConfig: safeJsonParse<Record<string, unknown>>((server.authConfig as string) ?? null, {}),
    capabilities: safeJsonParse<string[]>((server.capabilities as string) ?? null, []),
    metadata: safeJsonParse<Record<string, unknown>>((server.metadata as string) ?? null, {}),
  };
}

/** GET /api/mcp/servers/[id] — Get single server by ID */
export async function GET(_request: NextRequest, context: RouteContext) {
  try {
    const { id } = await context.params;

    const server = await db.mcpServer.findUnique({
      where: { id },
      include: {
        tools: { select: { id: true, name: true, displayName: true, status: true, riskLevel: true } },
      },
    });

    if (!server) {
      return NextResponse.json(
        { success: false, error: "Server not found", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    const response: ApiResponse<typeof server> = {
      success: true,
      data: deserializeServer(server),
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[GET /api/mcp/servers/[id]]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch server", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}

/** PUT /api/mcp/servers/[id] — Update server by ID */
export async function PUT(request: NextRequest, context: RouteContext) {
  try {
    const { id } = await context.params;

    const existing = await db.mcpServer.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Server not found", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    const body: Partial<ServerDTO> = await request.json();

    // If name is being changed, check for duplicates
    if (body.name && body.name !== existing.name) {
      const duplicate = await db.mcpServer.findUnique({ where: { name: body.name } });
      if (duplicate) {
        return NextResponse.json(
          { success: false, error: `Server with name "${body.name}" already exists`, code: "DUPLICATE" } as const,
          { status: 400 }
        );
      }
    }

    // Build update data — only include fields that are provided
    const updateData: Record<string, unknown> = {};
    if (body.name !== undefined) updateData.name = body.name;
    if (body.displayName !== undefined) updateData.displayName = body.displayName;
    if (body.description !== undefined) updateData.description = body.description;
    if (body.url !== undefined) updateData.url = body.url;
    if (body.protocol !== undefined) updateData.protocol = body.protocol;
    if (body.status !== undefined) updateData.status = body.status;
    if (body.healthCheckUrl !== undefined) updateData.healthCheckUrl = body.healthCheckUrl;
    if (body.authType !== undefined) updateData.authType = body.authType;
    if (body.authConfig !== undefined) updateData.authConfig = JSON.stringify(body.authConfig);
    if (body.capabilities !== undefined) updateData.capabilities = JSON.stringify(body.capabilities);
    if (body.metadata !== undefined) updateData.metadata = JSON.stringify(body.metadata);

    const server = await db.mcpServer.update({
      where: { id },
      data: updateData,
    });

    // Audit
    await recordAudit({
      action: "server.update",
      resource: "server",
      resourceId: server.id,
      resourceName: (server.name as string) ?? existing.name,
      severity: "info",
      outcome: "success",
      details: { updatedFields: Object.keys(updateData) },
    });

    const response: ApiResponse<typeof server> = {
      success: true,
      data: deserializeServer(server),
      message: "Server updated successfully",
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[PUT /api/mcp/servers/[id]]", error);
    return NextResponse.json(
      { success: false, error: "Failed to update server", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}

/** DELETE /api/mcp/servers/[id] — Delete server by ID */
export async function DELETE(_request: NextRequest, context: RouteContext) {
  try {
    const { id } = await context.params;

    const existing = await db.mcpServer.findUnique({
      where: { id },
      include: { _count: { select: { tools: true } } },
    });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Server not found", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    // Check if server has linked tools
    if (existing._count.tools > 0) {
      return NextResponse.json(
        {
          success: false,
          error: `Cannot delete server with ${existing._count.tools} linked tool(s). Unlink or delete tools first.`,
          code: "HAS_DEPENDENCIES",
        } as const,
        { status: 400 }
      );
    }

    await db.mcpServer.delete({ where: { id } });

    // Audit
    await recordAudit({
      action: "server.delete",
      resource: "server",
      resourceId: id,
      resourceName: existing.name,
      severity: "warn",
      outcome: "success",
      details: { displayName: existing.displayName, url: existing.url },
    });

    const response: ApiResponse<null> = {
      success: true,
      data: null,
      message: "Server deleted successfully",
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[DELETE /api/mcp/servers/[id]]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete server", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}

// ─── Helpers ────────────────────────────────────────────────────────

function safeJsonParse<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}
