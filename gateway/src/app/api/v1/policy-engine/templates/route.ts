// ─── Zenic-Agents v3 — Policy Engine API: Template List + Create ──────
// GET  /api/v1/policy-engine/templates          — List policy templates
// POST /api/v1/policy-engine/templates          — Create a policy template

import { NextRequest, NextResponse } from "next/server";
import { listTemplates, createTemplate } from "@/lib/policy-engine";
import type { PolicyTemplate } from "@/lib/policy-engine";

// GET /api/v1/policy-engine/templates
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const category = searchParams.get("category") ?? undefined;
    const industry = searchParams.get("industry") ?? undefined;
    const isActiveStr = searchParams.get("isActive");
    const limit = Number(searchParams.get("limit")) || undefined;
    const offset = Number(searchParams.get("offset")) || undefined;

    const isActive = isActiveStr !== null ? isActiveStr === "true" : undefined;

    const templates = await listTemplates({
      category,
      industry,
      isActive,
      limit,
      offset,
    });

    const data = templates.map((t) => ({
      templateId: t.templateId,
      name: t.name,
      version: t.version,
      description: t.description,
      category: t.category,
      industry: t.industry,
      tags: t.tags,
      parameterCount: t.parameters.length,
      constraintCount: t.constraints.length,
      generatedCount: t.generatedCount,
      isActive: t.isActive,
      author: t.author,
      contentHash: t.contentHash,
      createdAt: t.createdAt.toISOString(),
      updatedAt: t.updatedAt.toISOString(),
    }));

    return NextResponse.json({
      success: true,
      data,
      total: data.length,
    });
  } catch (error) {
    console.error("[PolicyEngine Templates GET]", error);
    return NextResponse.json(
      { success: false, error: "Failed to list templates", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}

// POST /api/v1/policy-engine/templates
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as PolicyTemplate;

    const record = await createTemplate(body);

    return NextResponse.json({
      success: true,
      data: {
        templateId: record.templateId,
        name: record.name,
        version: record.version,
        category: record.category,
        industry: record.industry,
        parameterCount: record.parameters.length,
        constraintCount: record.constraints.length,
        isActive: record.isActive,
        contentHash: record.contentHash,
        createdAt: record.createdAt.toISOString(),
      },
    }, { status: 201 });
  } catch (error) {
    if (error instanceof Error && error.name === "TemplateValidationError") {
      return NextResponse.json(
        { success: false, error: error.message, code: "VALIDATION_ERROR" },
        { status: 400 },
      );
    }
    console.error("[PolicyEngine Templates POST]", error);
    return NextResponse.json(
      { success: false, error: "Failed to create template", code: "INTERNAL_ERROR" },
      { status: 500 },
    );
  }
}
