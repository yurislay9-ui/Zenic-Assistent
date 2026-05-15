// ─── Zenic-Agents v3 — Policy Engine API: Versions ───────────────────
// GET /api/v1/policies/versions?policyId=xxx — List versions for a policy

import { NextRequest, NextResponse } from "next/server";
import { listVersions, getVersionChain } from "@/lib/policy-engine";

// GET /api/v1/policies/versions?policyId=xxx
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const policyId = searchParams.get("policyId");

    if (!policyId) {
      return NextResponse.json(
        { success: false, error: "policyId query parameter is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const chain = searchParams.get("chain") === "true";

    if (chain) {
      const versions = await getVersionChain(policyId);
      return NextResponse.json({
        success: true,
        data: versions,
      });
    }

    const status = searchParams.get("status") as "active" | "superseded" | "draft" | "archived" | undefined;
    const limit = Math.min(100, Math.max(1, Number(searchParams.get("limit")) || 20));
    const offset = Math.max(0, Number(searchParams.get("offset")) || 0);

    const result = await listVersions(policyId, { status, limit, offset });

    return NextResponse.json({
      success: true,
      data: result.versions,
      total: result.total,
    });
  } catch (error) {
    console.error("[Policy Versions GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch versions", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
