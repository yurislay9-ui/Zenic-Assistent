// ─── Zenic-Agents v3 — HITL API: Attach Evidence ─────────────────────
// POST /api/v1/hitl/evidence

import { NextRequest, NextResponse } from "next/server";
import { getEvidenceService } from "@/lib/hitl";

// POST /api/v1/hitl/evidence
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.requestId || !body.evidenceType || !body.content || !body.source) {
      return NextResponse.json(
        {
          success: false,
          error: "Missing required fields: requestId, evidenceType, content, source",
          code: "VALIDATION_ERROR",
        },
        { status: 400 },
      );
    }

    const validEvidenceTypes: string[] = ["screenshot", "log", "data_snapshot", "policy_result", "audit_record", "custom"];
    if (!validEvidenceTypes.includes(body.evidenceType)) {
      return NextResponse.json(
        { success: false, error: `Invalid evidenceType. Must be one of: ${validEvidenceTypes.join(", ")}`, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const service = getEvidenceService();
    const result = await service.attachEvidence(body.requestId, {
      evidenceType: body.evidenceType,
      content: body.content,
      source: body.source,
      description: body.description,
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
      if (error.message.includes("Invalid evidence type")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }
    console.error("[HITL POST evidence]", error);
    return NextResponse.json(
      { success: false, error: "Failed to attach evidence", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
