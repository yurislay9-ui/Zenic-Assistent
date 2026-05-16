// ─── MCP Servers CRUD — List & Create ───────────────────────────────

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { ApiResponse, PaginatedResponse, ServerDTO } from "@/lib/mcp-gateway/types";

/** Deserialize JSON fields on a server record */
function deserializeServer(server: Record<string, unknown>) {
  return {
    ...server,
    authConfig: safeJsonParse<Record<string, unknown>>((server.authConfig as string) ?? null, {}),
    capabilities: safeJsonParse<string[]>((server.capabilities as string) ?? null, []),
    metadata: safeJsonParse<Record<string, unknown>>((server.metadata as string) ?? null, {}),
  };
}

/** GET /api/mcp/servers — List servers with optional status filter & pagination */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    // Pagination
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20));

    // Filter
    const status = searchParams.get("status") || undefined;

    const where: Record<string, unknown> = {};
    if (status) where.status = status;

    const [total, servers] = await Promise.all([
      db.mcpServer.count({ where }),
      db.mcpServer.findMany({
        where,
        skip: (page - 1) * pageSize,
        take: pageSize,
        orderBy: { createdAt: "desc" },
        include: {
          _count: { select: { tools: true } },
        },
      }),
    ]);

    const data = servers.map((server) => ({
      ...deserializeServer(server),
      toolCount: server._count.tools,
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
    console.error("[GET /api/mcp/servers]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch servers", code: "INTERNAL_ERROR" } as const,
      { status: 500 }
    );
  }
}

/** POST /api/mcp/servers — Create a new server */
export async function POST(request: NextRequest) {
  try {
    const body: ServerDTO = await request.json();

    // Validate required fields
    const requiredFields: (keyof ServerDTO)[] = [
      "name", "displayName", "description", "url",
      "protocol", "status", "authType",
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
    const existing = await db.mcpServer.findUnique({ where: { name: body.name } });
    if (existing) {
      return NextResponse.json(
        { success: false, error: `Server with name "${body.name}" already exists`, code: "DUPLICATE" } as const,
        { status: 400 }
      );
    }

    const server = await db.mcpServer.create({
      data: {
        name: body.name,
        displayName: body.displayName,
        description: body.description,
        url: body.url,
        protocol: body.protocol,
        status: body.status,
        healthCheckUrl: body.healthCheckUrl ?? null,
        authType: body.authType,
        authConfig: JSON.stringify(body.authConfig ?? {}),
        capabilities: JSON.stringify(body.capabilities ?? []),
        metadata: JSON.stringify(body.metadata ?? {}),
      },
    });

    // Audit
    await recordAudit({
      action: "server.create",
      resource: "server",
      resourceId: server.id,
      resourceName: server.name,
      severity: "info",
      outcome: "success",
      details: { displayName: server.displayName, protocol: server.protocol, url: server.url },
    });

    const response: ApiResponse<typeof server> = {
      success: true,
      data: deserializeServer(server),
      message: "Server created successfully",
    };

    return NextResponse.json(response, { status: 201 });
  } catch (error) {
    console.error("[POST /api/mcp/servers]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create server", code: "INTERNAL_ERROR" } as const,
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
