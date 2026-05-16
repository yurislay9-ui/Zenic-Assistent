// ─── MCP Tools CRUD — List & Create ─────────────────────────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { ApiResponse, PaginatedResponse, ToolDTO } from "@/lib/mcp-gateway/types";

/** GET /api/mcp/tools — List tools with optional filters & pagination */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    // Pagination
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20));

    // Filters
    const category = searchParams.get("category") || undefined;
    const status = searchParams.get("status") || undefined;
    const riskLevel = searchParams.get("riskLevel") || undefined;
    const search = searchParams.get("search") || undefined;

    // Build where clause
    const where: Record<string, unknown> = {};
    if (category) where.category = category;
    if (status) where.status = status;
    if (riskLevel) where.riskLevel = riskLevel;
    if (search) {
      where.OR = [
        { name: { contains: search } },
        { displayName: { contains: search } },
        { description: { contains: search } },
      ];
    }

    const [total, tools] = await Promise.all([
      db.mcpTool.count({ where }),
      db.mcpTool.findMany({
        where,
        skip: (page - 1) * pageSize,
        take: pageSize,
        orderBy: { createdAt: "desc" },
        include: { server: { select: { id: true, name: true, displayName: true } } },
      }),
    ]);

    // Deserialize JSON fields for each tool
    const data = tools.map((tool) => ({
      ...tool,
      tags: safeJsonParse<string[]>(tool.tags, []),
      metadata: safeJsonParse<Record<string, unknown>>(tool.metadata, {}),
      inputSchema: safeJsonParse<Record<string, unknown>>(tool.inputSchema, {}),
      outputSchema: tool.outputSchema ? safeJsonParse<Record<string, unknown>>(tool.outputSchema, null) : null,
    }));

    const response: PaginatedResponse<typeof data[number]> = {
      success: true,
      data,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error("[GET /api/mcp/tools]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch tools", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}

/** POST /api/mcp/tools — Create a new tool */
export async function POST(request: NextRequest) {
  try {
    const body: ToolDTO = await request.json();

    // Validate required fields
    const requiredFields: (keyof ToolDTO)[] = [
      "name", "displayName", "description", "category",
      "version", "endpoint", "method", "inputSchema",
      "timeout", "retries", "rateLimit", "riskLevel", "status",
    ];

    for (const field of requiredFields) {
      if (body[field] === undefined || body[field] === null || body[field] === "") {
        return NextResponse.json(
          { success: false, error: `Missing required field: ${field}`, code: "VALIDATION_ERROR" } as const,
          { status: 400 }
        );
      }
    }

    // Check for duplicate name
    const existing = await db.mcpTool.findUnique({ where: { name: body.name } });
    if (existing) {
      return NextResponse.json(
        { success: false, error: `Tool with name "${body.name}" already exists`, code: "DUPLICATE" } as const,
        { status: 400 }
      );
    }

    // Validate serverId if provided
    if (body.serverId) {
      const server = await db.mcpServer.findUnique({ where: { id: body.serverId } });
      if (!server) {
        return NextResponse.json(
          { success: false, error: `Server with id "${body.serverId}" not found`, code: "VALIDATION_ERROR" } as const,
          { status: 400 }
        );
      }
    }

    const tool = await db.mcpTool.create({
      data: {
        name: body.name,
        displayName: body.displayName,
        description: body.description,
        category: body.category,
        version: body.version,
        icon: body.icon ?? null,
        endpoint: body.endpoint,
        method: body.method,
        inputSchema: typeof body.inputSchema === "string" ? body.inputSchema : JSON.stringify(body.inputSchema),
        outputSchema: body.outputSchema
          ? typeof body.outputSchema === "string" ? body.outputSchema : JSON.stringify(body.outputSchema)
          : null,
        timeout: body.timeout,
        retries: body.retries,
        rateLimit: body.rateLimit,
        riskLevel: body.riskLevel,
        status: body.status,
        requiresApproval: body.requiresApproval ?? false,
        tags: JSON.stringify(body.tags ?? []),
        metadata: JSON.stringify(body.metadata ?? {}),
        serverId: body.serverId ?? null,
      },
      include: { server: { select: { id: true, name: true, displayName: true } } },
    });

    // Audit
    await recordAudit({
      action: "tool.create",
      resource: "tool",
      resourceId: tool.id,
      resourceName: tool.name,
      severity: "info",
      outcome: "success",
      details: { displayName: tool.displayName, category: tool.category, riskLevel: tool.riskLevel },
    });

    const response: ApiResponse<typeof tool> = {
      success: true,
      data: {
        ...tool,
        tags: safeJsonParse<string[]>(tool.tags, []),
        metadata: safeJsonParse<Record<string, unknown>>(tool.metadata, {}),
        inputSchema: safeJsonParse<Record<string, unknown>>(tool.inputSchema, {}),
        outputSchema: tool.outputSchema ? safeJsonParse<Record<string, unknown>>(tool.outputSchema, null) : null,
      },
      message: "Tool created successfully",
    };

    return NextResponse.json(response, { status: 201 });
  } catch (error) {
    console.error("[POST /api/mcp/tools]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create tool", code: "INTERNAL_ERROR" } as const,
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
