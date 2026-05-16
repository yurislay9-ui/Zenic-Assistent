// ─── Zenic-Agents v3 — Phase 1 Policies (DEPRECATED) ──────────────────
// DEPRECATED: Use /api/v1/policies for declarative policy management
// This route is kept for backward compatibility with Phase 1 MCP Gateway.
// It operates on the AccessPolicy table (tool-level RBAC), while
// /api/v1/policies operates on the DeclPolicy table (declarative policies).

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { PaginatedResponse, PolicyDTO } from "@/lib/mcp-gateway/types";

/** Add deprecation headers to response */
function withDeprecation(response: NextResponse): NextResponse {
  response.headers.set("Deprecation", "true");
  response.headers.set(
    "Link",
    '</api/v1/policies>; rel="successor-version"',
  );
  response.headers.set(
    "X-Deprecated-Notice",
    "This endpoint is deprecated. Use /api/v1/policies for declarative policy management.",
  );
  return response;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20));

    const [policies, total] = await Promise.all([
      db.accessPolicy.findMany({
        include: {
          toolAccessPolicies: {
            include: { tool: { select: { id: true, name: true, displayName: true } } },
          },
        },
        orderBy: { priority: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.accessPolicy.count(),
    ]);

    // Parse JSON fields and map tool associations
    const data = policies.map((policy) => ({
      ...policy,
      conditions: safeJsonParse(policy.conditions),
      timeWindow: policy.timeWindow ? safeJsonParse(policy.timeWindow) : null,
      quota: policy.quota ? safeJsonParse(policy.quota) : null,
      tools: policy.toolAccessPolicies.map((tap) => tap.tool),
      toolAccessPolicies: undefined,
    }));

    const response: PaginatedResponse<typeof data[number]> = {
      success: true,
      data,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    };

    return withDeprecation(NextResponse.json(response));
  } catch (error) {
    console.error("[Policies GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch policies", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name, description, type, priority, isEnabled, conditions, effect, timeWindow, quota, toolIds } = body as PolicyDTO;

    if (!name || !effect) {
      return NextResponse.json(
        { success: false, error: "name and effect are required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Check for duplicate name
    const existing = await db.accessPolicy.findUnique({ where: { name } });
    if (existing) {
      return NextResponse.json(
        { success: false, error: `Policy "${name}" already exists`, code: "DUPLICATE" },
        { status: 409 },
      );
    }

    const policy = await db.accessPolicy.create({
      data: {
        name,
        description: description ?? "",
        type: type ?? "allow",
        priority: priority ?? 0,
        isEnabled: isEnabled ?? true,
        conditions: JSON.stringify(conditions ?? []),
        effect,
        timeWindow: timeWindow ? JSON.stringify(timeWindow) : null,
        quota: quota ? JSON.stringify(quota) : null,
        toolAccessPolicies: {
          create: (toolIds ?? []).map((toolId: string) => ({
            toolId,
          })),
        },
      },
      include: {
        toolAccessPolicies: {
          include: { tool: { select: { id: true, name: true, displayName: true } } },
        },
      },
    });

    await recordAudit({
      actorId: "api",
      action: "policy.create",
      resource: "policy",
      resourceId: policy.id,
      resourceName: policy.name,
      severity: "info",
      details: { name, effect, type, toolCount: toolIds?.length ?? 0 },
    });

    return withDeprecation(NextResponse.json({
      success: true,
      data: {
        ...policy,
        conditions: safeJsonParse(policy.conditions),
        timeWindow: policy.timeWindow ? safeJsonParse(policy.timeWindow) : null,
        quota: policy.quota ? safeJsonParse(policy.quota) : null,
        tools: policy.toolAccessPolicies.map((tap) => tap.tool),
        toolAccessPolicies: undefined,
      },
    }, { status: 201 }));
  } catch (error) {
    console.error("[Policies POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

function safeJsonParse(str: string | null): unknown {
  if (!str) return null;
  try {
    return JSON.parse(str);
  } catch {
    return str;
  }
}
