// ─── Zenic-Agents v3 — Policy Engine API: List + Create Policies ──────
// GET  /api/v1/policies          — List all declarative policies
// POST /api/v1/policies          — Create a new policy (JSON or YAML)

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { loadPolicyFromYaml, computeContentHash } from "@/lib/policy-engine";
import type { PolicyDocument } from "@/lib/policy-engine";

// GET /api/v1/policies
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const page = Math.max(1, Number(searchParams.get("page")) || 1);
    const pageSize = Math.min(100, Math.max(1, Number(searchParams.get("pageSize")) || 20));
    const isActive = searchParams.get("isActive");
    const category = searchParams.get("category");

    const where = {
      ...(isActive !== null ? { isActive: isActive === "true" } : {}),
    };

    const [policies, total] = await Promise.all([
      db.declPolicy.findMany({
        where,
        orderBy: { updatedAt: "desc" },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      db.declPolicy.count({ where }),
    ]);

    const data = policies.map((p) => ({
      policyId: p.policyId,
      name: p.name,
      description: p.description,
      version: p.version,
      labels: JSON.parse(p.labels),
      compliance: JSON.parse(p.compliance),
      statementCount: (JSON.parse(p.statements) as unknown[]).length,
      testCount: (JSON.parse(p.tests) as unknown[]).length,
      isActive: p.isActive,
      contentHash: p.contentHash,
      author: p.author,
      createdAt: p.createdAt.toISOString(),
      updatedAt: p.updatedAt.toISOString(),
    }));

    return NextResponse.json({
      success: true,
      data,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize),
    });
  } catch (error) {
    console.error("[Policies v1 GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to fetch policies", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// POST /api/v1/policies
export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers.get("content-type") ?? "";
    let document: PolicyDocument;
    let sourceYaml: string | undefined;

    if (contentType.includes("yaml") || contentType.includes("text/plain")) {
      // YAML input
      const yamlContent = await request.text();
      sourceYaml = yamlContent;
      document = loadPolicyFromYaml(yamlContent);
    } else {
      // JSON input
      const body = await request.json();
      if (body.yaml) {
        sourceYaml = body.yaml;
        document = loadPolicyFromYaml(body.yaml);
      } else if (body.apiVersion && body.kind && body.statements) {
        // Direct PolicyDocument
        document = body as PolicyDocument;
      } else {
        return NextResponse.json(
          { success: false, error: "Provide either a YAML string in 'yaml' field or a complete PolicyDocument", code: "VALIDATION_ERROR" },
          { status: 400 },
        );
      }
    }

    const contentHash = computeContentHash(document);

    // Check for duplicate policyId
    const existing = await db.declPolicy.findUnique({
      where: { policyId: document.metadata.id },
    });

    if (existing) {
      return NextResponse.json(
        { success: false, error: `Policy "${document.metadata.id}" already exists. Use PUT to update.`, code: "DUPLICATE" },
        { status: 409 },
      );
    }

    // Create the policy
    const policy = await db.declPolicy.create({
      data: {
        policyId: document.metadata.id,
        name: document.metadata.name,
        description: document.metadata.description,
        version: document.metadata.version,
        labels: JSON.stringify(document.metadata.labels ?? {}),
        compliance: JSON.stringify(document.metadata.compliance ?? []),
        statements: JSON.stringify(document.statements),
        tests: JSON.stringify(document.tests ?? []),
        sourceYaml: sourceYaml ?? null,
        contentHash,
        author: document.metadata.author ?? null,
      },
    });

    // Create initial version
    await db.declPolicyVersion.create({
      data: {
        declPolicyId: policy.id,
        version: document.metadata.version,
        contentHash,
        document: JSON.stringify(document),
        status: "active",
        createdBy: document.metadata.author ?? "system",
        changeDescription: "Initial version",
        parentVersionId: null,
      },
    });

    return NextResponse.json({
      success: true,
      data: {
        policyId: policy.policyId,
        name: policy.name,
        version: policy.version,
        contentHash: policy.contentHash,
        statementCount: document.statements.length,
        testCount: (document.tests ?? []).length,
        createdAt: policy.createdAt.toISOString(),
      },
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error && error.name === "PolicyValidationError") {
      return NextResponse.json(
        { success: false, error: error.message, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }
    if (error instanceof Error && error.name === "PolicyCompilationError") {
      return NextResponse.json(
        { success: false, error: error.message, code: "COMPILATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[Policies v1 POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create policy", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
