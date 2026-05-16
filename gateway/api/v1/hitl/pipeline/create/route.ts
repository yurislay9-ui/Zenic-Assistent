// ─── Zenic-Agents v3 — HITL API: Pipeline Create HITL Request ─────────
// POST /api/v1/hitl/pipeline/create
// Create HITL request from SafetyGate verdict or PolicyEngine requirement

import { NextRequest, NextResponse } from "next/server";
import { getPipelineIntegration } from "@/lib/hitl";

// POST /api/v1/hitl/pipeline/create
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.source) {
      return NextResponse.json(
        { success: false, error: "Missing required field: source (must be 'safety_gate' or 'policy_engine')", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    if (!body.requesterId || !body.requesterName) {
      return NextResponse.json(
        { success: false, error: "Missing required fields: requesterId, requesterName", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const integration = getPipelineIntegration();

    if (body.source === "safety_gate") {
      // Validate safety gate verdict
      if (!body.verdict || !body.verdict.actionId || !body.verdict.actionType || !body.verdict.verdict || !body.verdict.category) {
        return NextResponse.json(
          {
            success: false,
            error: "Missing required verdict fields: actionId, actionType, verdict, category",
            code: "VALIDATION_ERROR",
          },
          { status: 400 },
        );
      }

      const validVerdicts: string[] = ["confirm", "approve", "deny"];
      if (!validVerdicts.includes(body.verdict.verdict)) {
        return NextResponse.json(
          { success: false, error: `Invalid verdict. Must be one of: ${validVerdicts.join(", ")}`, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }

      const result = await integration.createFromSafetyGate(
        body.verdict,
        body.requesterId,
        body.requesterName,
        body.actionPayload,
      );

      if (!result) {
        return NextResponse.json({
          success: true,
          data: null,
          message: "Safety gate verdict was DENY — no HITL request created (DENY is invariant)",
        });
      }

      return NextResponse.json({
        success: true,
        data: result,
      }, { status: 201 });
    }

    if (body.source === "policy_engine") {
      // Validate policy engine requirement
      if (!body.requirement || !body.requirement.policyId || !body.requirement.statementId || !body.requirement.effect) {
        return NextResponse.json(
          {
            success: false,
            error: "Missing required requirement fields: policyId, statementId, effect",
            code: "VALIDATION_ERROR",
          },
          { status: 400 },
        );
      }

      const validEffects: string[] = ["require_approval", "escalate"];
      if (!validEffects.includes(body.requirement.effect)) {
        return NextResponse.json(
          { success: false, error: `Invalid effect. Must be one of: ${validEffects.join(", ")}`, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }

      if (!body.targetResource || !body.targetAction) {
        return NextResponse.json(
          { success: false, error: "Missing required fields: targetResource, targetAction", code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }

      const result = await integration.createFromPolicyEngine(
        body.requirement,
        body.requesterId,
        body.requesterName,
        body.targetResource,
        body.targetAction,
        body.actionPayload,
      );

      return NextResponse.json({
        success: true,
        data: result,
      }, { status: 201 });
    }

    return NextResponse.json(
      { success: false, error: "Invalid source. Must be 'safety_gate' or 'policy_engine'", code: "VALIDATION_ERROR" },
      { status: 400 },
    );
  } catch (error) {
    if (error instanceof Error) {
      if (error.message.includes("not found")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "NOT_FOUND" },
          { status: 404 },
        );
      }
      if (error.message.includes("validation failed")) {
        return NextResponse.json(
          { success: false, error: error.message, code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }
    console.error("[HITL POST pipeline/create]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create pipeline HITL request", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
