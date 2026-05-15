// ─── Zenic-Agents v3 — Policy Engine API: Deploy Approval ────────────
// POST /api/v1/policy-engine/approvals/[approvalId]/deploy  — Deploy an approved request

import { NextRequest, NextResponse } from "next/server";
import { deployApproval } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/approvals/[approvalId]/deploy
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ approvalId: string }> },
) {
  try {
    const { approvalId } = await params;

    const result = await deployApproval(approvalId);

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
      if (error.message.includes("Invalid state transition")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
      return NextResponse.json(
        { success: false, error: error.message, code: "DEPLOY_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Policy-Engine Deploy POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to deploy approval", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
