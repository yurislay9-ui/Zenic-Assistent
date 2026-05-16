// ─── Zenic-Agents v3 — HITL API: Provide Justification ───────────────
// POST /api/v1/hitl/justification

import { NextRequest, NextResponse } from "next/server";
import { getJustificationService } from "@/lib/hitl";

// POST /api/v1/hitl/justification
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.requestId || !body.reason || body.riskAcknowledgment === undefined || body.complianceCheck === undefined || !body.createdBy || !body.createdByName) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: requestId, reason, riskAcknowledgment, complianceCheck, createdBy, createdByName",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const service = getJustificationService();
    const result = await service.provideJustification(body.requestId, {
      reason: body.reason,
      riskAcknowledgment: body.riskAcknowledgment,
      complianceCheck: body.complianceCheck,
      businessJustification: body.businessJustification,
      createdBy: body.createdBy,
      createdByName: body.createdByName,
      decisionId: body.decisionId,
    });

    return NextResponse.json({
      success: true,
      data: result,
    }, { status: 201 });
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
    }
    console.error("[HITL POST justification]", error);
    return NextResponse.json(
      { success: false, error: "Failed to provide justification", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
