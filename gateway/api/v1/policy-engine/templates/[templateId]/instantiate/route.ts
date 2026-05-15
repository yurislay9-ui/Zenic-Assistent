// ─── Zenic-Agents v3 — Policy Engine API: Template Instantiate ────────
// POST /api/v1/policy-engine/templates/[templateId]/instantiate — Instantiate a template

import { NextRequest, NextResponse } from "next/server";
import { instantiateTemplate } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/templates/[templateId]/instantiate
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ templateId: string }> },
) {
  try {
    const { templateId } = await params;
    const body = await request.json() as {
      parameters: Record<string, unknown>;
      targetPolicyId?: string;
      autoDeploy: boolean;
      requestedBy: string;
    };

    const result = await instantiateTemplate({
      templateId,
      parameters: body.parameters ?? {},
      targetPolicyId: body.targetPolicyId,
      autoDeploy: body.autoDeploy ?? false,
      requestedBy: body.requestedBy ?? "api",
    });

    if (!result.success) {
      return NextResponse.json(
        { success: false, error: result.errors.join("; "), code: "INSTANTIATION_ERROR", warnings: result.warnings, unresolvedParameters: result.unresolvedParameters },
        { status: 400 },
      );
    }

    return NextResponse.json({
      success: true,
      data: {
        document: result.document,
        policyId: result.policyId,
        warnings: result.warnings,
        unresolvedParameters: result.unresolvedParameters,
      },
    }, { status: 201 });
  } catch (error) {
    console.error("[PolicyEngine Template Instantiate POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to instantiate template", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
