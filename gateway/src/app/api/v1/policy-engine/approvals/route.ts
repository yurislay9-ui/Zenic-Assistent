// ─── Zenic-Agents v3 — Policy Engine API: Approvals ──────────────────
// GET  /api/v1/policy-engine/approvals  — List approval requests
// POST /api/v1/policy-engine/approvals  — Create an approval request

import { NextRequest, NextResponse } from "next/server";
import {
  createApprovalRequest,
  listApprovalRequests,
} from "@/lib/policy-engine";
import type { CreateApprovalRequestInput } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/approvals
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get("status") ?? undefined;
    const priority = searchParams.get("priority") ?? undefined;
    const requestedBy = searchParams.get("requestedBy") ?? undefined;
    const targetPolicyId = searchParams.get("targetPolicyId") ?? undefined;
    const limit = Math.min(200, Math.max(1, Number(searchParams.get("limit")) || 50));
    const offset = Math.max(0, Number(searchParams.get("offset")) || 0);

    const { requests, total } = await listApprovalRequests({
      status: status as "draft" | "pending_review" | "approved" | "rejected" | "cancelled" | "expired" | "deployed" | "rolled_back" | undefined,
      priority: priority as "low" | "medium" | "high" | "critical" | "emergency" | undefined,
      requestedBy,
      targetPolicyId,
      limit,
      offset,
    });

    return NextResponse.json({
      success: true,
      data: requests,
      total,
      limit,
      offset,
    });
  } catch (error) {
    console.error("[Policy-Engine Approvals GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to list approval requests", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// POST /api/v1/policy-engine/approvals
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validate required fields
    if (!body.title || !body.description || !body.proposedDocument || !body.requestedBy) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: title, description, proposedDocument, requestedBy",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const input: CreateApprovalRequestInput = {
      title: body.title,
      description: body.description,
      proposedDocument: body.proposedDocument,
      targetPolicyId: body.targetPolicyId,
      previousVersion: body.previousVersion,
      requestedBy: body.requestedBy,
      requiredReviewerRoles: body.requiredReviewerRoles,
      autoApproveRules: body.autoApproveRules,
      expiryHours: body.expiryHours,
    };

    const result = await createApprovalRequest(input);

    return NextResponse.json({
      success: true,
      data: result,
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error) {
      // Distinguish validation errors from internal errors
      if (error.message.includes("must have") || error.message.includes("Invalid state transition")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
      return NextResponse.json(
        { success: false, error: error.message, code: "APPROVAL_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Policy-Engine Approvals POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create approval request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
