// ─── DEPRECATED: Use /api/v1/policies instead ─────────────────────────
// This route operates on the AccessPolicy model (Phase 1 RBAC).
// For the full declarative policy engine, use /api/v1/policies (DeclPolicy).

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { PaginatedResponse, PolicyDTO } from "@/lib/mcp-gateway/types";

/** @deprecated Use /api/v1/policies for the declarative policy engine */
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

    return NextResponse.json(response, {
      headers: { "Deprecation": "true", "Link": "</api/v1/policies>; rel=\"successor-version\"" },
    });
  } catch (error) {
    console.error("[Policies GET] [DEPRECATED]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch policies", code: "INTERNAL_ERROR" },
      { status: 500 }
    );
  }
}

/** @deprecated Use POST /api/v1/policies for the declarative policy engine */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name, description, type, priority, isEnabled, conditions, effect, timeWindow, quota, toolIds } = body as PolicyDTO;

    if (!name || !effect) {
      return NextResponse.json(
        { success: false, error: "name and effect are required", code: "VALIDATION_ERROR" },
        { status: 400 }
      );
    }

    const existing = await db.accessPolicy.findUnique({ where: { name } });
    if (existing) {
      return NextResponse.json(
        { success: false, error: `Policy "${name}" already exists`, code: "DUPLICATE" },
        { status: 409 }
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

    return NextResponse.json({
      success: true,
      data: {
        ...policy,
        conditions: safeJsonParse(policy.conditions),
        timeWindow: policy.timeWindow ? safeJsonParse(policy.timeWindow) : null,
        quota: policy.quota ? safeJsonParse(policy.quota) : null,
        tools: policy.toolAccessPolicies.map((tap) => tap.tool),
        toolAccessPolicies: undefined,
      },
    }, {
      status: 201,
      headers: { "Deprecation": "true", "Link": "</api/v1/policies>; rel=\"successor-version\"" },
    });
  } catch (error) {
    console.error("[Policies POST] [DEPRECATED]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create policy", code: "INTERNAL_ERROR" },
      { status: 500 }
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
