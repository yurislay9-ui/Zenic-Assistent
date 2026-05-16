// ─── Zenic-Agents v3 — Policy Engine API: Evaluate ───────────────────
// POST /api/v1/policies/evaluate — Evaluate a request against all active policies

import { NextRequest, NextResponse } from "next/server";
import { getPolicyEvaluator } from "@/lib/policy-engine";
import type { PolicyEvaluationRequest } from "@/lib/policy-engine";

// POST /api/v1/policies/evaluate
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as PolicyEvaluationRequest;

    if (!body.resource || !body.action) {
      return NextResponse.json(
        { success: false, error: "resource and action are required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const evaluator = getPolicyEvaluator();
    const result = await evaluator.evaluate({
      resource: body.resource,
      action: body.action,
      context: body.context ?? {},
      tenantId: body.tenantId,
      userId: body.userId,
      roles: body.roles,
    });

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    console.error("[Policy Evaluate POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to evaluate policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
