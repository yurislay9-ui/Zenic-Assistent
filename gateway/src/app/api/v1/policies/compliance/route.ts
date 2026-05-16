// ─── Zenic-Agents v3 — Policy Engine API: Compliance Report ──────────
// GET /api/v1/policies/compliance?policyId=xxx — Generate compliance report

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { generateComplianceReport } from "@/lib/policy-engine";
import type { PolicyDocument } from "@/lib/policy-engine";

// GET /api/v1/policies/compliance?policyId=xxx
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

    const policy = await db.declPolicy.findUnique({ where: { policyId } });
    if (!policy) {
      return NextResponse.json(
        { success: false, error: `Policy "${policyId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const document: PolicyDocument = {
      apiVersion: policy.apiVersion,
      kind: "PolicyDocument",
      metadata: {
        id: policy.policyId,
        name: policy.name,
        version: policy.version,
        description: policy.description,
        compliance: JSON.parse(policy.compliance),
        labels: JSON.parse(policy.labels),
        author: policy.author ?? undefined,
        createdAt: policy.createdAt.toISOString(),
        updatedAt: policy.updatedAt.toISOString(),
      },
      statements: JSON.parse(policy.statements),
      tests: JSON.parse(policy.tests),
    };

    const report = generateComplianceReport(document);

    return NextResponse.json({
      success: true,
      data: report,
    });
  } catch (error) {
    console.error("[Policy Compliance GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to generate compliance report", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
