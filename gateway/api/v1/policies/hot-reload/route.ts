// ─── Zenic-Agents v3 — Policy Engine API: Hot-Reload ────────────────
// POST /api/v1/policies/hot-reload — Trigger policy reload

import { NextRequest, NextResponse } from "next/server";
import { getPolicyHotReloader } from "@/lib/policy-engine";

// POST /api/v1/policies/hot-reload
export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const reloader = getPolicyHotReloader();

    // Check if reloading a specific policy from YAML
    if (body.policyId && body.yaml) {
      const document = await reloader.reloadFromYaml(body.policyId, body.yaml);
      return NextResponse.json({
        success: true,
        data: {
          policyId: body.policyId,
          version: document.metadata.version,
          reloaded: true,
        },
      });
    }

    // Reload all policies
    const result = await reloader.reloadAll();
    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[Policy Hot-Reload POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to reload policies", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
