// ─── Zenic-Agents v3 — Playbooks API: Compliance Report ─────────────
// GET /api/v1/playbooks/compliance — Get compliance report for a playbook

import { NextRequest, NextResponse } from "next/server";
import { mapPlaybookCompliance } from "@/lib/playbooks";

// GET /api/v1/playbooks/compliance
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

    const report = await mapPlaybookCompliance(playbookId);

    return NextResponse.json(report);
  } catch (error) {
    console.error("[Playbooks Compliance GET]", error);
    return NextResponse.json(
      { error: "Failed to generate compliance report", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
