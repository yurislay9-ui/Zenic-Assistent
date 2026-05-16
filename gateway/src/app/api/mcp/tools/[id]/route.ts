// ─── MCP Tools CRUD — Get / Update / Delete by ID ──────────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { ApiResponse, ToolDTO } from "@/lib/mcp-gateway/types";

interface RouteContext {
  params: Promise<{ id: string }>;
}

/** Deserialize JSON fields on a tool record */
function deserializeTool(tool: Record<string, unknown>) {
  return {
    ...tool,
    tags: safeJsonParse<string[]>((tool.tags as string) ?? null, []),
    metadata: safeJsonParse<Record<string, unknown>>((tool.metadata as string) ?? null, {}),
    inputSchema: safeJsonParse<Record<string, unknown>>((tool.inputSchema as string) ?? null, {}),
    outputSchema: tool.outputSchema
      ? safeJsonParse<Record<string, unknown>>(tool.outputSchema as string, null)
      : null,
  };
}

/** GET /api/mcp/tools/[id] — Get single tool by ID */
export async function GET(_request: NextRequest, context: RouteContext) {
  try {
    const { id } = await context.params;

    const tool = await db.mcpTool.findUnique({
      where: { id },
      include: { server: { select: { id: true, name: true, displayName: true } } },
    });

    if (!tool) {
      return NextResponse.json(
        { success: false, error: "Tool not found", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    const response: ApiResponse<typeof tool> = {
      success: true,
      data: deserializeTool(tool),
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[GET /api/mcp/tools/[id]]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch tool", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}

/** PUT /api/mcp/tools/[id] — Update tool by ID */
export async function PUT(request: NextRequest, context: RouteContext) {
  try {
    const { id } = await context.params;

    const existing = await db.mcpTool.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Tool not found", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    const body: Partial<ToolDTO> = await request.json();

    // If name is being changed, check for duplicates
    if (body.name && body.name !== existing.name) {
      const duplicate = await db.mcpTool.findUnique({ where: { name: body.name } });
      if (duplicate) {
        return NextResponse.json(
          { success: false, error: `Tool with name "${body.name}" already exists`, code: "DUPLICATE" } as const,
          { status: 400 }
        );
      }
    }

    // Validate serverId if provided
    if (body.serverId !== undefined && body.serverId !== null) {
      const server = await db.mcpServer.findUnique({ where: { id: body.serverId } });
      if (!server) {
        return NextResponse.json(
          { success: false, error: `Server with id "${body.serverId}" not found`, code: "VALIDATION_ERROR" } as const,
          { status: 400 }
        );
      }
    }

    // Build update data — only include fields that are provided
    const updateData: Record<string, unknown> = {};
    if (body.displayName !== undefined) updateData.displayName = body.displayName;
    if (body.description !== undefined) updateData.description = body.description;
    if (body.name !== undefined) updateData.name = body.name;
    if (body.category !== undefined) updateData.category = body.category;
    if (body.version !== undefined) updateData.version = body.version;
    if (body.icon !== undefined) updateData.icon = body.icon;
    if (body.endpoint !== undefined) updateData.endpoint = body.endpoint;
    if (body.method !== undefined) updateData.method = body.method;
    if (body.inputSchema !== undefined) {
      updateData.inputSchema = typeof body.inputSchema === "string"
        ? body.inputSchema
        : JSON.stringify(body.inputSchema);
    }
    if (body.outputSchema !== undefined) {
      updateData.outputSchema = body.outputSchema
        ? typeof body.outputSchema === "string" ? body.outputSchema : JSON.stringify(body.outputSchema)
        : null;
    }
    if (body.timeout !== undefined) updateData.timeout = body.timeout;
    if (body.retries !== undefined) updateData.retries = body.retries;
    if (body.rateLimit !== undefined) updateData.rateLimit = body.rateLimit;
    if (body.riskLevel !== undefined) updateData.riskLevel = body.riskLevel;
    if (body.status !== undefined) updateData.status = body.status;
    if (body.requiresApproval !== undefined) updateData.requiresApproval = body.requiresApproval;
    if (body.tags !== undefined) updateData.tags = JSON.stringify(body.tags);
    if (body.metadata !== undefined) updateData.metadata = JSON.stringify(body.metadata);
    if (body.serverId !== undefined) updateData.serverId = body.serverId;

    const tool = await db.mcpTool.update({
      where: { id },
      data: updateData,
      include: { server: { select: { id: true, name: true, displayName: true } } },
    });

    // Audit
    await recordAudit({
      action: "tool.update",
      resource: "tool",
      resourceId: tool.id,
      resourceName: (tool.name as string) ?? existing.name,
      severity: "info",
      outcome: "success",
      details: { updatedFields: Object.keys(updateData) },
    });

    const response: ApiResponse<typeof tool> = {
      success: true,
      data: deserializeTool(tool),
      message: "Tool updated successfully",
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[PUT /api/mcp/tools/[id]]", error);
    return NextResponse.json(
      { success: false, error: "Failed to update tool", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}

/** DELETE /api/mcp/tools/[id] — Delete tool by ID (only if not system) */
export async function DELETE(_request: NextRequest, context: RouteContext) {
  try {
    const { id } = await context.params;

    const existing = await db.mcpTool.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Tool not found", code: "NOT_FOUND" } as const,
        { status: 404 }
      );
    }

    // Check if tool is a system tool (via metadata.isSystem convention)
    let metadata: Record<string, unknown> = {};
    try {
      metadata = JSON.parse(existing.metadata);
    } catch {
      // ignore parse errors
    }
    if (metadata.isSystem === true) {
      return NextResponse.json(
        { success: false, error: "Cannot delete system tool", code: "FORBIDDEN" } as const,
        { status: 400 }
      );
    }

    await db.mcpTool.delete({ where: { id } });

    // Audit
    await recordAudit({
      action: "tool.delete",
      resource: "tool",
      resourceId: id,
      resourceName: existing.name,
      severity: "warn",
      outcome: "success",
      details: { displayName: existing.displayName, category: existing.category },
    });

    const response: ApiResponse<null> = {
      success: true,
      data: null,
      message: "Tool deleted successfully",
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[DELETE /api/mcp/tools/[id]]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete tool", code: "INTERNAL_ERROR" } as const,
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
