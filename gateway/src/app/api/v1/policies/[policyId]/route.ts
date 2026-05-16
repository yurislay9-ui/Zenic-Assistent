// ─── Zenic-Agents v3 — Policy Engine API: Get/Update/Delete Policy ────
// GET    /api/v1/policies/[policyId]   — Get a single policy
// PUT    /api/v1/policies/[policyId]   — Update a policy (creates new version)
// DELETE /api/v1/policies/[policyId]   — Deactivate a policy

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { loadPolicyFromYaml, computeContentHash, createVersion } from "@/lib/policy-engine";
import type { PolicyDocument } from "@/lib/policy-engine";

// GET /api/v1/policies/[policyId]
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ policyId: string }> },
) {
  try {
    const { policyId } = await params;
    const policy = await db.declPolicy.findUnique({ where: { policyId } });

    if (!policy) {
      return NextResponse.json(
        { success: false, error: `Policy "${policyId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    return NextResponse.json({
      success: true,
      data: {
        policyId: policy.policyId,
        name: policy.name,
        description: policy.description,
        apiVersion: policy.apiVersion,
        version: policy.version,
        labels: JSON.parse(policy.labels),
        compliance: JSON.parse(policy.compliance),
        statements: JSON.parse(policy.statements),
        tests: JSON.parse(policy.tests),
        isActive: policy.isActive,
        sourceYaml: policy.sourceYaml,
        contentHash: policy.contentHash,
        author: policy.author,
        createdAt: policy.createdAt.toISOString(),
        updatedAt: policy.updatedAt.toISOString(),
      },
    });
  } catch (error) {
    console.error("[Policy GET by ID]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// PUT /api/v1/policies/[policyId]
export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ policyId: string }> },
) {
  try {
    const { policyId } = await params;
    const existing = await db.declPolicy.findUnique({ where: { policyId } });

    if (!existing) {
      return NextResponse.json(
        { success: false, error: `Policy "${policyId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    const contentType = request.headers.get("content-type") ?? "";
    let document: PolicyDocument;
    let sourceYaml: string | undefined;

    if (contentType.includes("yaml") || contentType.includes("text/plain")) {
      const yamlContent = await request.text();
      sourceYaml = yamlContent;
      document = loadPolicyFromYaml(yamlContent);
    } else {
      const body = await request.json();
      if (body.yaml) {
        sourceYaml = body.yaml;
        document = loadPolicyFromYaml(body.yaml);
      } else if (body.apiVersion && body.statements) {
        document = body as PolicyDocument;
      } else {
        return NextResponse.json(
          { success: false, error: "Provide either YAML or PolicyDocument", code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }

    if (document.metadata.id !== policyId) {
      return NextResponse.json(
        { success: false, error: `Document metadata.id "${document.metadata.id}" does not match URL policyId "${policyId}"`, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }

    const version = await createVersion({
      policyId,
      document,
      changeDescription: `Updated to v${document.metadata.version}`,
      createdBy: document.metadata.author ?? "api",
    });

    if (sourceYaml) {
      await db.declPolicy.update({
        where: { policyId },
        data: { sourceYaml },
      });
    }

    return NextResponse.json({
      success: true,
      data: {
        policyId,
        version: version.version,
        contentHash: version.contentHash,
        status: version.status,
        createdAt: version.createdAt,
      },
    });
  } catch (error) {
    if (error instanceof Error && (error.name === "PolicyValidationError" || error.name === "PolicyCompilationError")) {
      return NextResponse.json(
        { success: false, error: error.message, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Policy PUT]", error);
    return NextResponse.json(
      { success: false, error: "Failed to update policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// DELETE /api/v1/policies/[policyId]
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ policyId: string }> },
) {
  try {
    const { policyId } = await params;
    const existing = await db.declPolicy.findUnique({ where: { policyId } });

    if (!existing) {
      return NextResponse.json(
        { success: false, error: `Policy "${policyId}" not found`, code: "NOT_FOUND" },
        { status: 404 },
      );
    }

    await db.declPolicy.update({
      where: { policyId },
      data: { isActive: false, updatedAt: new Date() },
    });

    return NextResponse.json({
      success: true,
      data: { policyId, deactivated: true },
    });
  } catch (error) {
    console.error("[Policy DELETE]", error);
    return NextResponse.json(
      { success: false, error: "Failed to deactivate policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
