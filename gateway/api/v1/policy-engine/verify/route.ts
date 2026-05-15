// ─── Zenic-Agents v3 — Policy Engine API: Verify (Formal Verification) ─
// POST /api/v1/policy-engine/verify  — Verify policies (formal verification)
// GET  /api/v1/policy-engine/verify  — List verification results

import { NextRequest, NextResponse } from "next/server";
import { verifyPolicies, listVerifications } from "@/lib/policy-engine";
import type { SolverType, VerificationStatus } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/verify
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as {
      policyIds?: string[];
      solverType?: SolverType;
    };

    const result = await verifyPolicies({
      policyIds: body.policyIds,
      solverType: body.solverType,
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[PolicyEngine Verify POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to verify policies", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// GET /api/v1/policy-engine/verify
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get("status") as VerificationStatus | null;
    const consistentStr = searchParams.get("consistent");
    const limit = Number(searchParams.get("limit")) || undefined;
    const offset = Number(searchParams.get("offset")) || undefined;

    const consistent = consistentStr !== null ? consistentStr === "true" : undefined;

    const results = await listVerifications({
      status: status ?? undefined,
      consistent,
      limit,
      offset,
    });

    return NextResponse.json({
      success: true,
      data: results,
      total: results.length,
    });
  } catch (error) {
    console.error("[PolicyEngine Verify GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to list verifications", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
