// ─── Zenic-Agents v3 — Policy Engine API: Approval by ID ─────────────
// GET /api/v1/policy-engine/approvals/[approvalId]  — Get an approval request

import { NextRequest, NextResponse } from "next/server";
import { getApprovalRequest } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/approvals/[approvalId]
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ approvalId: string }> },
) {
  try {
    const { approvalId } = await params;

    const result = await getApprovalRequest(approvalId);

    if (!result) {
      return NextResponse.json(
        { success: false, error: `Approval request "${approvalId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[Policy-Engine Approval GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch approval request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
