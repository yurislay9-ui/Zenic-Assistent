// ─── Zenic-Agents v3 — Playbooks API: Activate Playbook ─────────────
// POST /api/v1/playbooks/activate — Activate a playbook for a tenant

import { NextRequest, NextResponse } from "next/server";
import { getPlaybookEngine } from "@/lib/playbooks";
import type { PlaybookActivationRequest, PricingTierName } from "@/lib/playbooks";
import { PricingTierName as PricingTierNameEnum } from "@/lib/playbooks";

// POST /api/v1/playbooks/activate
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { playbookId, tenantId, selectedTier, customConfig } = body;

    if (!playbookId) {
      return NextResponse.json(
        { error: "playbookId is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    if (!selectedTier) {
      return NextResponse.json(
        { error: "selectedTier is required (starter, pro, or enterprise)", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Validate selectedTier value
    const validTiers: PricingTierName[] = [
      PricingTierNameEnum.STARTER,
      PricingTierNameEnum.PRO,
      PricingTierNameEnum.ENTERPRISE,
    ];
    if (!validTiers.includes(selectedTier)) {
      return NextResponse.json(
        { error: `Invalid selectedTier "${selectedTier}". Must be one of: starter, pro, enterprise`, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const activationRequest: PlaybookActivationRequest = {
      playbookId,
      tenantId: tenantId ?? "default",
      selectedTier,
      customConfig,
    };

    const engine = getPlaybookEngine();
    const result = await engine.activatePlaybook(activationRequest);

    if (!result.success) {
      return NextResponse.json(
        { error: result.message, code: "ACTIVATION_FAILED" },
        { status: 422 },
      );
    }

    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    console.error("[Playbooks Activate POST]", error);
    return NextResponse.json(
      { error: "Failed to activate playbook", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
