// ─── Zenic-Agents v3 — HITL API: Coordinator Full Approve ────────────
// POST /api/v1/hitl/coordinator/approve

import { NextRequest, NextResponse } from "next/server";
import { getHITLCoordinator } from "@/lib/hitl";

// POST /api/v1/hitl/coordinator/approve
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.requestId) {
      return NextResponse.json(
        { success: false, error: "Missing required field: requestId", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    if (!body.decisionBy || !body.decisionByName || !body.role) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: decisionBy, decisionByName, role",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    if (!body.reason || body.riskAcknowledgment === undefined || body.complianceCheck === undefined) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing justification fields: reason, riskAcknowledgment, complianceCheck",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const coordinator = getHITLCoordinator();
    const result = await coordinator.fullApprove(
      body.requestId,
      {
        decisionBy: body.decisionBy,
        decisionByName: body.decisionByName,
        role: body.role,
        comment: body.comment,
        delegatedFrom: body.delegatedFrom,
      },
      {
        reason: body.reason,
        riskAcknowledgment: body.riskAcknowledgment,
        complianceCheck: body.complianceCheck,
        businessJustification: body.businessJustification,
        createdBy: body.createdBy ?? body.decisionBy,
        createdByName: body.createdByName ?? body.decisionByName,
        decisionId: body.decisionId,
      },
    );

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
      if (error.message.includes("validation failed")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
      if (error.message.includes("Cannot approve") || error.message.includes("already approved")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "CONFLICT" },
          { status: 409 },
        );
      }
    }
    console.error("[HITL POST coordinator/approve]", error);
    return NextResponse.json(
      { success: false, error: "Failed to approve request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
