// ─── Zenic-Agents v3 — Playbooks API: Certification ─────────────────
// POST /api/v1/playbooks/certification — Request certification
// GET  /api/v1/playbooks/certification — Verify certification status

import { NextRequest, NextResponse } from "next/server";
import { requestCertification, verifyCertification } from "@/lib/playbooks";

// POST /api/v1/playbooks/certification
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { playbookId, requestedBy, justification } = body;

    if (!playbookId) {
      return NextResponse.json(
        { error: "playbookId is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    if (!requestedBy) {
      return NextResponse.json(
        { error: "requestedBy is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    if (!justification) {
      return NextResponse.json(
        { error: "justification is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const result = await requestCertification(playbookId, requestedBy, justification);

    if (!result.success) {
      return NextResponse.json(
        { error: result.error, code: "CERTIFICATION_FAILED" },
        { status: 422 },
      );
    }

    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    console.error("[Playbooks Certification POST]", error);
    return NextResponse.json(
      { error: "Failed to request certification", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// GET /api/v1/playbooks/certification
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const playbookId = searchParams.get("playbookId");

    if (!playbookId) {
      return NextResponse.json(
        { error: "playbookId query parameter is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const verification = await verifyCertification(playbookId);

    return NextResponse.json(verification);
  } catch (error) {
    console.error("[Playbooks Certification GET]", error);
    return NextResponse.json(
      { error: "Failed to verify certification", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
