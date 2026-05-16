// ─── Zenic-Agents v3 — Policy Engine API: Diff ───────────────────────
// GET /api/v1/policies/diff?policyId=xxx&fromVersion=1.0.0&toVersion=2.0.0

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { diffPolicies, formatDiffSummary } from "@/lib/policy-engine";
import type { PolicyDocument } from "@/lib/policy-engine";

// GET /api/v1/policies/diff?policyId=xxx&fromVersion=1.0.0&toVersion=2.0.0
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const policyId = searchParams.get("policyId");
    const fromVersion = searchParams.get("fromVersion");
    const toVersion = searchParams.get("toVersion");

    if (!policyId || !fromVersion || !toVersion) {
      return NextResponse.json(
        { success: false, error: "policyId, fromVersion, and toVersion are required", code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    // Find the policy
    const policy = await db.declPolicy.findUnique({ where: { policyId } });
    if (!policy) {
      return NextResponse.json(
        { success: false, error: `Policy "${policyId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    // Get both versions
    const [fromVer, toVer] = await Promise.all([
      db.declPolicyVersion.findUnique({
        where: { declPolicyId_version: { declPolicyId: policy.id, version: fromVersion } },
      }),
      db.declPolicyVersion.findUnique({
        where: { declPolicyId_version: { declPolicyId: policy.id, version: toVersion } },
      }),
    ]);

    if (!fromVer) {
      return NextResponse.json(
        { success: false, error: `Version "${fromVersion}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    if (!toVer) {
      return NextResponse.json(
        { success: false, error: `Version "${toVersion}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const fromDoc = JSON.parse(fromVer.document) as PolicyDocument;
    const toDoc = JSON.parse(toVer.document) as PolicyDocument;

    const diff = diffPolicies(fromDoc, toDoc);

    return NextResponse.json({
      success: true,
      data: diff,
      summary: formatDiffSummary(diff),
    });
  } catch (error) {
    console.error("[Policy Diff GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to compute diff", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
