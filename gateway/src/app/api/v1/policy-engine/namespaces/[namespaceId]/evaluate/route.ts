// ─── Zenic-Agents v3 — Policy Engine API: Namespace Evaluate ──────────
// POST /api/v1/policy-engine/namespaces/[namespaceId]/evaluate — Evaluate a request within a namespace

import { NextRequest, NextResponse } from "next/server";
import { evaluateInNamespace } from "@/lib/policy-engine";
import type { PolicyEvaluationRequest } from "@/lib/policy-engine";

// POST /api/v1/policy-engine/namespaces/[namespaceId]/evaluate
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ namespaceId: string }> },
) {
  try {
    const { namespaceId } = await params;
    const body = await request.json() as PolicyEvaluationRequest;

    if (!body.resource || !body.action) {
      return NextResponse.json(
        { success: false, error: "resource and action are required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const result = await evaluateInNamespace(body, namespaceId);

    return NextResponse.json({
      success: true,
      data: result,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "NamespaceError") {
      const code = (error as { code: string }).code;
      const status = code === "NAMESPACE_NOT_FOUND" ? 404 : 400;
      return NextResponse.json(
        { success: false, error: error.message, code },
        { status },
      );
    }
    console.error("[PolicyEngine Namespace Evaluate POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to evaluate in namespace", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
