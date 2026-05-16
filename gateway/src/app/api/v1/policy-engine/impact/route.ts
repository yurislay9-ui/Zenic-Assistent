// ─── Zenic-Agents v3 — Policy Engine API: Impact Analysis ────────────
// POST /api/v1/policy-engine/impact  — Analyze impact of a policy change
// GET  /api/v1/policy-engine/impact  — List impact analyses

import { NextRequest, NextResponse } from "next/server";
import { analyzeImpact, listImpactAnalyses } from "@/lib/policy-engine";
import type { ImpactAnalysisRequest, ImpactAnalysisDepth } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/impact
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as {
      policyId: string;
      proposedVersion?: string;
      proposedDocument?: unknown;
      depth?: ImpactAnalysisDepth;
      requestedBy: string;
    };

    if (!body.policyId) {
      return NextResponse.json(
        { success: false, error: "policyId is required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const result = await analyzeImpact({
      policyId: body.policyId,
      proposedVersion: body.proposedVersion,
      proposedDocument: body.proposedDocument as ImpactAnalysisRequest["proposedDocument"],
      depth: body.depth ?? "standard",
      requestedBy: body.requestedBy ?? "api",
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to analyze impact";
    return NextResponse.json(
      { success: false, error: message, code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// GET /api/v1/policy-engine/impact
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const policyId = searchParams.get("policyId") ?? undefined;

    const results = await listImpactAnalyses(policyId);

    return NextResponse.json({
      success: true,
      data: results,
      total: results.length,
    });
  } catch (error) {
    console.error("[PolicyEngine Impact GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to list impact analyses", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
