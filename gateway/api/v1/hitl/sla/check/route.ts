// ─── Zenic-Agents v3 — HITL API: Check and Process SLA Breaches ──────
// POST /api/v1/hitl/sla/check

import { NextResponse } from "next/server";
import { getSLAService } from "@/lib/hitl";

// POST /api/v1/hitl/sla/check
export async function POST() {
  try {
    const service = getSLAService();

    // 1. Check for SLA breaches
    const breached = await service.checkSLABreaches();

    // 2. Auto-escalate breached requests
    const escalated = await service.autoEscalateBreached();

    return NextResponse.json({
      success: true,
      data: {
        breached,
        escalated,
      },
    });
  } catch (error) {
    console.error("[HITL POST sla/check]", error);
    return NextResponse.json(
      { success: false, error: "Failed to check SLA breaches", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
