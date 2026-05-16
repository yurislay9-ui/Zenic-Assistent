// ─── Zenic-Agents v3 — HITL API: Get + Update Approval Request ────────
// GET  /api/v1/hitl/[requestId] — Get request detail
// PUT  /api/v1/hitl/[requestId] — Update request

import { NextRequest, NextResponse } from "next/server";
import { getApprovalEngine, getAuditTrail, getApprovalTimeline, verifyAuditIntegrity } from "@/lib/hitl";

interface RouteParams {
  params: Promise<{ requestId: string }>;
}

// GET /api/v1/hitl/[requestId]
export async function GET(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;
    const { searchParams } = new URL(request.url);
    const includeTimeline = searchParams.get("timeline") === "true";
    const includeAudit = searchParams.get("audit") === "true";
    const verifyIntegrity = searchParams.get("verify") === "true";

    const engine = getApprovalEngine();
    const approvalRequest = await engine.getRequest(requestId);

    if (!approvalRequest) {
      return NextResponse.json(
        { success: false, error: `Approval request "${requestId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const result: Record<string, unknown> = { ...approvalRequest };

    if (includeTimeline) {
      result.timeline = await getApprovalTimeline(requestId);
    }

    if (includeAudit) {
      result.auditTrail = await getAuditTrail(requestId);
    }

    if (verifyIntegrity) {
      result.integrityVerification = await verifyAuditIntegrity(requestId);
    }

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[HITL GET requestId]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch approval request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// PUT /api/v1/hitl/[requestId]
export async function PUT(
  request: NextRequest,
  { params }: RouteParams,
) {
  try {
    const { requestId } = await params;
    const body = await request.json();

    const engine = getApprovalEngine();
    const result = await engine.updateRequest(requestId, {
      title: body.title,
      description: body.description,
      priority: body.priority,
      deadline: body.deadline,
      tags: body.tags,
      metadata: body.metadata,
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    if (error instanceof Error) {
      if (error.message.includes("not found")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "NOT_FOUND" },
          { status: 404 },
        );
      }
      if (error.message.includes("Cannot update")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "CONFLICT" },
          { status: 409 },
        );
      }
    }
    console.error("[HITL PUT requestId]", error);
    return NextResponse.json(
      { success: false, error: "Failed to update approval request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
