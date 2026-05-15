// ─── Zenic-Agents v3 — Playbooks API: ROI Calculation ───────────────
// GET /api/v1/playbooks/roi — Get ROI calculation for a playbook

import { NextRequest, NextResponse } from "next/server";
import { calculateRoiFromPlaybook, formatRoiReport } from "@/lib/playbooks";
import { db } from "@/lib/db";

// GET /api/v1/playbooks/roi
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

    // Look up the internal DB id for the playbook
    const playbook = await db.playbook.findFirst({
      where: { playbookId },
    });

    if (!playbook) {
      return NextResponse.json(
        { error: `Playbook "${playbookId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const roi = await calculateRoiFromPlaybook(playbook.id);
    const formatted = formatRoiReport(roi);

    return NextResponse.json({
      roi,
      formatted,
    });
  } catch (error) {
    console.error("[Playbooks ROI GET]", error);
    return NextResponse.json(
      { error: "Failed to calculate ROI", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
