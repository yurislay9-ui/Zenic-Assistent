// ─── Zenic-Agents v3 — Phase 1 Policy by ID (DEPRECATED) ────────────
// DEPRECATED: Use /api/v1/policies/[policyId] for declarative policy management
// This route is kept for backward compatibility with Phase 1 MCP Gateway.
// It operates on the AccessPolicy table (tool-level RBAC), while
// /api/v1/policies/[policyId] operates on the DeclPolicy table.

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { recordAudit } from "@/lib/mcp-gateway/services/audit-service";
import type { PolicyDTO } from "@/lib/mcp-gateway/types";

/** Add deprecation headers to response */
function withDeprecation(response: NextResponse): NextResponse {
  response.headers.set("Deprecation", "true");
  response.headers.set(
    "Link",
    '</api/v1/policies>; rel="successor-version"',
  );
  response.headers.set(
    "X-Deprecated-Notice",
    "This endpoint is deprecated. Use /api/v1/policies/[policyId] for declarative policy management.",
  );
  return response;
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const policy = await db.accessPolicy.findUnique({
      where: { id },
      include: {
        toolAccessPolicies: {
          include: { tool: { select: { id: true, name: true, displayName: true } } },
        },
      },
    });

    if (!policy) {
      return NextResponse.json(
        { success: false, error: "Policy not found", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

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
    }));
  } catch (error) {
    console.error("[Policy GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const existing = await db.accessPolicy.findUnique({ where: { id } });
    if (!existing) {
      return NextResponse.json(
        { success: false, error: "Policy not found", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const body = await request.json();
    const { name, description, type, priority, isEnabled, conditions, effect, timeWindow, quota, toolIds } = body as Partial<PolicyDTO>;

    // Update policy fields
    const updatedPolicy = await db.accessPolicy.update({
      where: { id },
      data: {
        ...(name !== undefined && { name }),
        ...(description !== undefined && { description }),
        ...(type !== undefined && { type }),
        ...(priority !== undefined && { priority }),
        ...(isEnabled !== undefined && { isEnabled }),
        ...(conditions !== undefined && { conditions: JSON.stringify(conditions) }),
        ...(effect !== undefined && { effect }),
        ...(timeWindow !== undefined && { timeWindow: timeWindow ? JSON.stringify(timeWindow) : null }),
        ...(quota !== undefined && { quota: quota ? JSON.stringify(quota) : null }),
      },
    });

    // If toolIds provided, replace all tool-policy associations
    if (Array.isArray(toolIds)) {
      await db.toolAccessPolicy.deleteMany({ where: { policyId: id } });
      if (toolIds.length > 0) {
        await db.toolAccessPolicy.createMany({
          data: toolIds.map((toolId: string) => ({
            toolId,
            policyId: id,
          })),
        });
      }
    }

    // Fetch updated with associations
    const policyWithTools = await db.accessPolicy.findUnique({
      where: { id },
      include: {
        toolAccessPolicies: {
          include: { tool: { select: { id: true, name: true, displayName: true } } },
        },
      },
    });

    await recordAudit({
      actorId: "api",
      action: "policy.update",
      resource: "policy",
      resourceId: id,
      resourceName: updatedPolicy.name,
      severity: "info",
      details: {
        updatedFields: Object.keys(body),
        toolCount: toolIds?.length ?? policyWithTools?.toolAccessPolicies.length,
      },
    });

    return withDeprecation(NextResponse.json({
      success: true,
      data: {
        ...policyWithTools,
        conditions: safeJsonParse(policyWithTools!.conditions),
        timeWindow: policyWithTools!.timeWindow ? safeJsonParse(policyWithTools!.timeWindow) : null,
        quota: policyWithTools!.quota ? safeJsonParse(policyWithTools!.quota) : null,
        tools: policyWithTools!.toolAccessPolicies.map((tap) => tap.tool),
        toolAccessPolicies: undefined,
      },
    }));
  } catch (error) {
    console.error("[Policy PUT]", error);
    return NextResponse.json(
      { success: false, error: "Failed to update policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    const policy = await db.accessPolicy.findUnique({ where: { id } });
    if (!policy) {
      return NextResponse.json(
        { success: false, error: "Policy not found", code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    // Delete policy (cascades will handle ToolAccessPolicy)
    await db.accessPolicy.delete({ where: { id } });

    await recordAudit({
      actorId: "api",
      action: "policy.delete",
      resource: "policy",
      resourceId: id,
      resourceName: policy.name,
      severity: "warn",
      details: { deletedPolicy: policy.name },
    });

    return withDeprecation(NextResponse.json({
      success: true,
      data: { id, name: policy.name },
      message: "Policy deleted successfully",
    }));
  } catch (error) {
    console.error("[Policy DELETE]", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete policy", code: "INTERNAL_ERROR" },
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
