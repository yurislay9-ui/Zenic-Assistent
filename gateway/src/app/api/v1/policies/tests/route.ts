// ─── Zenic-Agents v3 — Policy Engine API: Test Runner ────────────────
// POST /api/v1/policies/tests?policyId=xxx — Run tests for a policy
// GET  /api/v1/policies/tests?policyId=xxx — Get test results history

import { NextRequest, NextResponse } from "next/server";
import { runAndStoreTests, getTestResults } from "@/lib/policy-engine";

// POST /api/v1/policies/tests?policyId=xxx
export async function POST(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const policyId = searchParams.get("policyId");

    if (!policyId) {
      return NextResponse.json(
        { success: false, error: "policyId query parameter is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const result = await runAndStoreTests(policyId, "manual");

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    if (error instanceof Error && error.message.includes("not found")) {
      return NextResponse.json(
        { success: false, error: error.message, code: "NOT_FOUND" },
        { status: 404 },
      );
    }
    console.error("[Policy Tests POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to run policy tests", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// GET /api/v1/policies/tests?policyId=xxx
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

    const limit = Math.min(50, Math.max(1, Number(searchParams.get("limit")) || 20));
    const offset = Math.max(0, Number(searchParams.get("offset")) || 0);

    const result = await getTestResults(policyId, { limit, offset });

    return NextResponse.json({
      success: true,
      data: result.results,
      total: result.total,
    });
  } catch (error) {
    console.error("[Policy Tests GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch test results", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
