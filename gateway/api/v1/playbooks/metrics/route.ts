// ─── Zenic-Agents v3 — Playbooks API: Operational Metrics ───────────
// GET /api/v1/playbooks/metrics — Get playbook operational metrics

import { NextRequest, NextResponse } from "next/server";
import { collectPlaybookMetrics } from "@/lib/playbooks";
import { db } from "@/lib/db";

// GET /api/v1/playbooks/metrics
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const playbookId = searchParams.get("playbookId");
    const tenantId = searchParams.get("tenantId") ?? undefined;

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

    const snapshot = await collectPlaybookMetrics(playbook.id, tenantId);

    return NextResponse.json(snapshot);
  } catch (error) {
    console.error("[Playbooks Metrics GET]", error);
    return NextResponse.json(
      { error: "Failed to collect playbook metrics", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
