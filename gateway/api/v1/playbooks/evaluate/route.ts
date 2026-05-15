// ─── Zenic-Agents v3 — Playbooks API: Evaluate Playbook ─────────────
// POST /api/v1/playbooks/evaluate — Evaluate a playbook for a tenant

import { NextRequest, NextResponse } from "next/server";
import { getPlaybookEngine } from "@/lib/playbooks";

// POST /api/v1/playbooks/evaluate
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { playbookId, tenantId } = body;

    if (!playbookId) {
      return NextResponse.json(
        { error: "playbookId is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const engine = getPlaybookEngine();
    const result = await engine.evaluatePlaybook(playbookId, tenantId);

    return NextResponse.json(result);
  } catch (error) {
    console.error("[Playbooks Evaluate POST]", error);
    return NextResponse.json(
      { error: "Failed to evaluate playbook", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
