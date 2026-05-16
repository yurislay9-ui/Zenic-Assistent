// ─── Zenic-Agents v3 — Policy Engine API: Submit for Review ──────────
// POST /api/v1/policy-engine/approvals/[approvalId]/review  — Submit for review

import { NextRequest, NextResponse } from "next/server";
import { submitForReview } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/approvals/[approvalId]/review
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ approvalId: string }> },
) {
  try {
    const { approvalId } = await params;

    const result = await submitForReview(approvalId);

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
      if (error.message.includes("Invalid state transition") || error.message.includes("missing required fields")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
      return NextResponse.json(
        { success: false, error: error.message, code: "REVIEW_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Policy-Engine Review POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to submit for review", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
