// ─── Zenic-Agents v3 — Policy Engine API: Approve / Reject ───────────
// POST /api/v1/policy-engine/approvals/[approvalId]/decide  — Approve or reject

import { NextRequest, NextResponse } from "next/server";
import { approveRequest } from "@/lib/policy-engine";
import type { ApprovalDecision } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/approvals/[approvalId]/decide
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ approvalId: string }> },
) {
  try {
    const { approvalId } = await params;
    const body = await request.json();

    // Validate required fields
    if (!body.decision || !body.reviewerId || !body.reviewerName || !body.role) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: decision (approved|rejected), reviewerId, reviewerName, role",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    // Validate decision value
    if (body.decision !== "approved" && body.decision !== "rejected") {
      return NextResponse.json(
        {
          success: false,
          error: "Decision must be 'approved' or 'rejected'",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const decision: ApprovalDecision = {
      reviewerId: body.reviewerId,
      reviewerName: body.reviewerName,
      decision: body.decision,
      role: body.role,
      comment: body.comment ?? "",
      decidedAt: new Date().toISOString(),
    };

    const result = await approveRequest(approvalId, decision);

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
      if (
        error.message.includes("not authorized") ||
        error.message.includes("already submitted") ||
        error.message.includes("Cannot add decision") ||
        error.message.includes("Invalid state transition")
      ) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
      return NextResponse.json(
        { success: false, error: error.message, code: "DECISION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Policy-Engine Decide POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to process decision", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
